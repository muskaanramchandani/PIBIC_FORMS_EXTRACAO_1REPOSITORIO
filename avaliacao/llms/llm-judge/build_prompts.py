"""
Gera os prompts completos do LLM as a judge: um arquivo por sistema,
execução e lote, pronto para colar numa sessão nova.

Uso: python3 build_prompts.py <csvs> <sistemas>

  <csvs>      pasta com os `avaliacao-<sistema>.csv`
  <sistemas>  pasta com um diretório por sistema; os artefatos da
              reconstrução ficam em `<sistema>/artefatos/`, e os
              prompts são escritos ao lado

Cada arquivo tem duas partes, `# SYSTEM` e `# USER`, para colar juntas
numa conversa ou mandar separadas pela API. O `manifest.csv` diz que
linhas e que semente cada arquivo usou.
"""

import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent

EXECUTIONS = 3
BATCH = 10

#: Acima disso os artefatos (menos `microfrontends.json`) vão recortados
#: ao que as linhas do lote envolvem.
WHOLE_LIMIT = 200_000

ARTIFACTS = [
    "microfrontends", "compositions", "navigations",
    "communications", "api_calls", "state_accesses",
]


def system_prompt() -> str:
    """O System e os exemplos do template, sem as notas para nós."""

    text = (HERE / "template.md").read_text(encoding="utf-8")
    body = text[text.index("## System"):text.index("## User")]

    keep = []

    for line in body.splitlines():
        if line.startswith("## System") or line.strip() == "---":
            continue
        if line.startswith("Tirados do catálogo:") or line.startswith("> "):
            continue
        keep.append(line)

    return "\n".join(keep).strip() + "\n"


def load(system: Path) -> dict:

    data = {name: json.loads((system / f"{name}.json").read_text()) for name in ARTIFACTS}

    # As não direcionadas são pares de estado global, que repetem
    # `state_accesses.json` — a página também não as mostra.
    data["communications"] = [item for item in data["communications"] if item.get("directed")]

    return data


def detections(system: Path) -> list[dict]:
    return json.loads((system / "detections.json").read_text())


def rows(path: Path) -> tuple[list[str], list[list[str]]]:

    with path.open(encoding="utf-8-sig", newline="") as handle:
        table = list(csv.reader(handle))

    return table[0], table[1:]


def short(name: str) -> str:
    return name.rpartition("/")[2] or name


def cut(data: dict, batch: list[list[str]], by_number: dict) -> dict:
    """Só o que as linhas do lote envolvem; `microfrontends` inteiro."""

    mfes: set[str] = set()
    paths: set[str] = set()
    slices: set[str] = set()

    for row in batch:
        detection = by_number.get(row[0])
        if not detection:
            continue
        mfes.update(detection.get("subjects") or [])
        metadata = detection.get("metadata") or {}
        if metadata.get("path"):
            paths.add(metadata["path"])
        slices.update(metadata.get("slices") or {})

    def touches(*names):
        return any(name in mfes for name in names)

    return {
        "microfrontends": data["microfrontends"],
        "compositions": [item for item in data["compositions"] if touches(item["consumer"], item["provider"])],
        "navigations": [item for item in data["navigations"] if touches(item["source"], item["target"])],
        "communications": [item for item in data["communications"] if touches(item["source"], item["target"])],
        "api_calls": [item for item in data["api_calls"] if item["path"] in paths],
        "state_accesses": [
            item for item in data["state_accesses"] if f"{item['library']}:{item['path']}" in slices
        ],
    }


def user_prompt(system: str, data: dict, header: list[str], batch: list[list[str]]) -> str:

    parts = [f"Sistema: {system}", ""]

    for name in ARTIFACTS:
        parts += [f"{name}.json:", json.dumps(data[name], ensure_ascii=False), ""]

    lines = [header] + batch
    table = "\n".join(",".join(_cell(value) for value in row) for row in lines)

    parts += ["Planilha a preencher:", table, ""]

    return "\n".join(parts)


def _cell(value: str) -> str:
    return f'"{value}"' if "," in value or '"' in value else value


def main(csvs: str, output: str) -> None:

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    prompt = system_prompt()
    manifest = [["arquivo", "sistema", "execucao", "lote", "semente", "linhas"]]

    for path in sorted(Path(csvs).glob("avaliacao-*.csv")):

        name = path.stem.removeprefix("avaliacao-")
        system = out / name / "artefatos"
        header, items = rows(path)
        data = load(system)
        found = detections(system)

        # O CSV tem as detecções na ordem do `detections.json`, com o `#`
        # contado na avaliação inteira: a posição liga uma ao outro.
        if len(found) != len(items):
            raise SystemExit(f"{name}: {len(items)} linhas no CSV e {len(found)} detecções")
        by_number = {row[0]: detection for row, detection in zip(items, found)}

        whole = sum(len(json.dumps(data[key])) for key in ARTIFACTS if key != "microfrontends") <= WHOLE_LIMIT

        for execution in range(1, EXECUTIONS + 1):

            # A semente é do sistema e da execução: a mesma entrada dá
            # sempre a mesma ordem, e cada execução tem a sua.
            seed = f"{name}-{execution}"
            order = items[:]
            random.Random(seed).shuffle(order)

            for start in range(0, len(order), BATCH):

                batch = order[start:start + BATCH]
                number = start // BATCH + 1
                given = data if whole else cut(data, batch, by_number)

                file = out / name / f"execucao-{execution}-lote-{number:02d}.md"
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(
                    "# SYSTEM\n\n" + prompt + "\n# USER\n\n" + user_prompt(name, given, header, batch),
                    encoding="utf-8",
                )

                manifest.append([
                    str(file.relative_to(out)), name, execution, number, seed,
                    " ".join(row[0] for row in batch),
                ])

    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(manifest)

    print(f"{len(manifest) - 1} prompts em {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
