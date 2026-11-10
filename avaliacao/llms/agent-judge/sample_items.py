"""
Sorteia os itens que o agente confere.

Uso: python3 sample_items.py

Lê `sistemas/<sistema>/artefatos/` e escreve `amostra.csv`. Por tipo, o
tamanho vem da fórmula de Cochran (95% de confiança, margem de 10%, com
correção para população finita), repartido entre os sistemas na
proporção dos itens de cada um, no mínimo 1 onde houver.
"""

import csv
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).parent
SYSTEMS = HERE / "sistemas"

Z = 1.96
MARGIN = 0.10
SEED = "agent-judge-amostra"


def cochran(population: int) -> int:

    if not population:
        return 0

    n0 = Z * Z * 0.25 / (MARGIN * MARGIN)

    return min(population, math.ceil(n0 / (1 + (n0 - 1) / population)))


def where(location: dict | None) -> str:
    return f"{location['file']}:{location['line']}" if location and location.get("file") else ""


def short(name: str) -> str:
    return name.rpartition("/")[2] or name


def items(folder: Path) -> dict[str, list[dict]]:
    """Todos os itens do sistema, por tipo, cada um com o que afirma."""

    def load(name):
        return json.loads((folder / f"{name}.json").read_text())

    found: dict[str, list[dict]] = {}

    def add(kind, claim, location):
        found.setdefault(kind, []).append({"tipo": kind, "afirma": claim, "onde": location})

    for unit in load("microfrontends"):

        add("micro frontend",
            f"{unit['id']} é uma unidade implantável separada, no diretório {unit['directory']}"
            + (f", com ponto de entrada {unit['entrypoint']}" if unit.get("entrypoint") else ""),
            unit.get("entrypoint") or unit["directory"])

        for screen in unit["screens"]:
            add("tela",
                f"o componente {screen['component']} é uma tela de {short(unit['id'])}"
                + (f", na rota {screen['route']}" if screen.get("route") else ""),
                where(screen))

        for fragment in unit["fragments"]:
            add("fragmento",
                f"{short(unit['id'])} expõe o componente {fragment['name']} para outros micro frontends montarem",
                where(fragment))

    for item in load("compositions"):
        add("composição",
            f"{short(item['consumer'])} monta o fragmento {item['fragment']} de {short(item['provider'])}",
            where(item.get("imported_at")))

    for item in load("navigations"):
        add("navegação",
            f"{short(item['source'])} leva o usuário para {item.get('resolved_url') or item.get('expression')}, "
            f"rota de {short(item['target'])}",
            where(item.get("at")))

    for item in load("communications"):
        if not item.get("directed"):
            continue
        produced = item.get("produced_at") or [{}]
        add("comunicação",
            f"{short(item['source'])} publica a mensagem {item['channel']} ({item['mechanism']}) "
            f"que {short(item['target'])} recebe",
            where(produced[0]))

    for item in load("api_calls"):
        add("chamada de API",
            f"{short(item['microfrontend'])} chama {item['method']} {item['path']}",
            where(item.get("at")))

    for item in load("state_accesses"):
        verb = "lê" if item["access"] == "read" else "grava"
        add("acesso a estado",
            f"{short(item['microfrontend'])} {verb} a chave {item['path']} de {item['library']}",
            where(item.get("at")))

    return found


def allocate(total: int, sizes: dict[str, int]) -> dict[str, int]:
    """Repartição proporcional, pelos maiores restos, com mínimo 1 onde houver."""

    present = {name: size for name, size in sizes.items() if size}
    population = sum(present.values())

    if not population:
        return {}

    share = {name: max(1, math.floor(total * size / population)) for name, size in present.items()}
    remainders = sorted(present, key=lambda name: -(total * present[name] / population) % 1)

    for name in remainders:
        if sum(share.values()) >= total:
            break
        if share[name] < present[name]:
            share[name] += 1

    return {name: min(share[name], present[name]) for name in present}


def main() -> None:

    by_system = {folder.name: items(folder / "artefatos") for folder in sorted(SYSTEMS.iterdir()) if folder.is_dir()}
    kinds = sorted({kind for found in by_system.values() for kind in found})

    rows = [["sistema", "id", "tipo", "afirma", "onde"]]
    summary = []

    for kind in kinds:

        sizes = {name: len(found.get(kind, [])) for name, found in by_system.items()}
        total = cochran(sum(sizes.values()))
        shares = allocate(total, sizes)

        for name, count in sorted(shares.items()):
            chosen = random.Random(f"{SEED}-{kind}-{name}").sample(by_system[name][kind], count)
            for index, item in enumerate(chosen, 1):
                rows.append([name, f"{kind.replace(' ', '-')}-{index:03d}", kind, item["afirma"], item["onde"]])

        summary.append((kind, sum(sizes.values()), total, sum(shares.values())))

    with (HERE / "amostra.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)

    for kind, population, wanted, drawn in summary:
        print(f"{kind:16} N={population:5}  Cochran={wanted:4}  sorteados={drawn:4}")
    print(f"total sorteado: {len(rows) - 1}")


if __name__ == "__main__":
    main()
