"""
Gera os CSVs da avaliação das detecções do DAMFE.

Uso: python3 build_sheet.py <pasta com um diretório por sistema> <pasta de saída>

Cada diretório de sistema tem o `detections.json` do `damfe detect`.
"""

import csv
import json
import sys
from pathlib import Path


#: Os que o DAMFE detecta, avaliados ou não: a caracterização pergunta
#: por todos, inclusive Cyclic e Hub-like, que não tiveram detecção.
KNOWN = [
    "Cyclic Dependency",
    "Hub-like Dependency",
    "One Micro Frontend for All",
    "Hammering APIs",
    "Global State Communication",
    "Mega Frontend",
    "Nano Frontend",
]


def short(name: str) -> str:
    return name.rpartition("/")[2] or name


def items(root: Path) -> list[dict]:

    found = []

    for system in sorted(path for path in root.iterdir() if (path / "detections.json").is_file()):

        for detection in json.loads((system / "detections.json").read_text()):

            name = detection["anti_pattern"]
            metadata = detection.get("metadata") or {}
            subjects = detection.get("subjects") or []

            # O hammering é por endpoint: sem ele, as linhas de um
            # sistema com os mesmos micro frontends ficariam iguais.
            endpoint = metadata.get("path", "") if name == "hammering-apis" else ""

            found.append(
                {
                    "system": system.name,
                    "anti_pattern": name,
                    "microfrontends": ", ".join(short(item) for item in subjects),
                    "endpoint": endpoint,
                }
            )

    return found


def write(path: Path, rows: list[list]) -> None:

    # utf-8-sig: o Excel só lê acento em CSV com BOM.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(rows)


def about() -> list[list]:

    questions = [
        "VOCÊ",
        "Cargo / papel atual",
        "Anos de experiência com micro frontends",
        "Tecnologias que já usou para desenvolver micro frontends (single-spa, Module Federation, implementação própria da empresa, outra)",
        "ANTI-PADRÕES",
    ]

    for name in KNOWN:
        questions += [
            f"{name}: já viu na prática? (sim/não/não sei)",
        ]

    return [["pergunta", "resposta"]] + [[question, ""] for question in questions]


def evaluation(found: list[dict]) -> dict[str, list[list]]:
    """Uma tabela por sistema: cada uma vira uma aba ao importar."""

    tables: dict[str, list[list]] = {}

    # O número é do item na avaliação inteira, não no sistema: a
    # análise junta as abas e precisa de um identificador único.
    for number, item in enumerate(found, 1):

        rows = tables.setdefault(item["system"], [
            ["#", "anti-padrão", "micro frontends", "endpoint",
             "julgamento (Sim/Não/Não sei)", "justificativa (se Não ou Não sei)"],
        ])

        rows.append([number, item["anti_pattern"], item["microfrontends"], item["endpoint"], "", ""])

    return tables


def main(root: str, output: str) -> None:

    found = items(Path(root))

    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)

    for system, rows in evaluation(found).items():
        write(folder / f"avaliacao-{system}.csv", rows)
    write(folder / "sobre-voce.csv", about())

    print(f"{len(found)} itens em {folder}")


if __name__ == "__main__":
    main(*sys.argv[1:])
