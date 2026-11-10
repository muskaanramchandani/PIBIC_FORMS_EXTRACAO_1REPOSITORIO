"""
Junta o que faltou nas 3 execuções de cada modelo.

Uso: python3 faltou_resumo.py

Dois itens são a mesma omissão quando têm o mesmo tipo e uma evidência
no mesmo arquivo, a até 3 linhas uma da outra. Uma omissão conta quando
aparece em 2 das 3 execuções. Escreve `faltou/omissoes.csv`, uma linha
por omissão e modelo, para a conferência no código.
"""

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
RUNS = HERE / "runs-faltou"
OUT = HERE / "faltou" / "omissoes.csv"
MODELS = ["deepseek-deepseek-v4-pro", "openai-gpt-5-mini"]
NEAR = 3


def places(item: dict) -> set[tuple[str, int]]:
    """(arquivo, linha) de cada evidência; o arquivo pelo nome e a pasta de cima, que o caminho varia."""

    found = set()

    for text in item.get("evidencia") or []:
        match = re.match(r"\s*(.+?):(\d+)", str(text))
        if match:
            parts = Path(match.group(1)).parts[-2:]
            found.add(("/".join(parts), int(match.group(2))))

    return found


def same(first: dict, second: dict) -> bool:
    return first["tipo"] == second["tipo"] and any(
        a == c and abs(b - d) <= NEAR for a, b in places(first) for c, d in places(second))


def main() -> None:

    rows = []

    for model in MODELS:

        # Uma pasta por sistema; na amostra extra do udistrital, uma por MFE abaixo dela.
        for folder in sorted({path.parent for path in (RUNS / model).rglob("execucao-*.json")}):

            groups: list[dict] = []

            for execution in (1, 2, 3):
                record = folder / f"execucao-{execution}.json"
                data = json.loads(record.read_text()) if record.exists() else {}
                if not data.get("ok"):
                    continue
                for item in data["missing"]:
                    group = next((g for g in groups if any(same(item, other) for other in g["items"])), None)
                    if group is None:
                        groups.append(group := {"items": [], "executions": set()})
                    group["items"].append(item)
                    group["executions"].add(execution)

            for group in groups:
                if len(group["executions"]) >= 2:
                    first = group["items"][0]
                    rows.append({
                        "sistema": folder.relative_to(RUNS / model).parts[0],
                        "amostra": "extra" if folder.parent != RUNS / model else "principal", "modelo": model, "execucoes": len(group["executions"]),
                        "mfe": first.get("mfe"), "tipo": first["tipo"], "descricao": first.get("descricao"),
                        "evidencia": "; ".join(first.get("evidencia") or []),
                    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{OUT.name}: {len(rows)} omissões")


if __name__ == "__main__":
    main()
