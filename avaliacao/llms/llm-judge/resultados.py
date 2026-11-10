"""
Resume os julgamentos do LLM as a judge.

Uso: python3 resultados.py

Lê `respostas/<modelo>/execucao-<n>/avaliacao-<sistema>.csv` e escreve
`resultados.md`: por juiz, quanto ele concorda com as detecções (pela
maioria das 3 execuções), por anti-padrão; a estabilidade entre as
execuções; e a concordância entre os juízes.

Ficam de fora o nabstore e o halloween, que não vieram da mineração, e
o piloto do `openai/gpt-5`, que não tem as 3 execuções. Concordância pelo kappa de Cohen (entre as 3
execuções, a média dos 3 pares).
"""

import collections
import csv
import itertools
from pathlib import Path

HERE = Path(__file__).parent

JUDGES = [
    "openai-gpt-6-luna",
    "qwen-qwen3.7-plus",
    "nvidia-nemotron-3-ultra-550b-a55b-free",
]
EXECUTIONS = (1, 2, 3)
EXCLUDED = {"nabstore", "halloween"}
JUDGMENTS = ["Sim", "Não", "Não sei"]

#: No empate, o mais severo com a detecção.
SEVERITY = ["Não", "Não sei", "Sim"]

MISSING = "(sem resposta)"

BEGIN = "<!-- início do trecho gerado por resultados.py -->"
END = "<!-- fim do trecho gerado -->"


def share(hits: int, total: int) -> str:

    return f"{hits / total:.0%}" if total else "—"


def majority(votes: list[str]) -> str:

    votes = [vote for vote in votes if vote in JUDGMENTS]

    if not votes:
        return MISSING

    counts = collections.Counter(votes)
    top = max(counts.values())

    return next(item for item in SEVERITY if counts.get(item) == top)


def cohen(pairs: list[tuple[str, str]]) -> float | None:
    """Kappa de Cohen entre dois avaliadores."""

    if not pairs:
        return None

    observed = sum(1 for a, b in pairs if a == b) / len(pairs)
    first = collections.Counter(a for a, _ in pairs)
    second = collections.Counter(b for _, b in pairs)
    chance = sum(first[key] * second[key] for key in first) / (len(pairs) ** 2)

    return (observed - chance) / (1 - chance) if chance < 1 else 1.0


def light(table: list[list[str]]) -> float | None:
    """Média do kappa de Cohen dos pares de avaliadores (Light, 1971), para as 3 execuções."""

    if not table:
        return None

    values = [cohen([(row[i], row[j]) for row in table]) for i, j in itertools.combinations(range(len(table[0])), 2)]

    return sum(values) / len(values)


def load(judge: str) -> dict[tuple[str, int], dict]:
    """(sistema, #) → linha: anti-padrão, micro frontends, endpoint e o julgamento de cada execução."""

    items: dict[tuple[str, int], dict] = {}

    for execution in EXECUTIONS:

        for path in sorted((HERE / "respostas" / judge / f"execucao-{execution}").glob("avaliacao-*.csv")):

            system = path.stem.removeprefix("avaliacao-")

            if system in EXCLUDED:
                continue

            with path.open(newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))[1:]

            for row in rows:
                number, anti_pattern, subjects, endpoint, judgment = (row + [""] * 5)[:5]
                item = items.setdefault(
                    (system, int(number)),
                    {"anti_pattern": anti_pattern, "subjects": subjects, "endpoint": endpoint, "votes": {}},
                )
                item["votes"][execution] = judgment.strip() if judgment.strip() in JUDGMENTS else MISSING

    return items


def main() -> None:

    out = ["# LLM as a judge — resultados", ""]
    out.append(
        "Gerado por `resultados.py` a partir de `respostas/`. Sem nabstore e halloween (160 detecções). "
        "Veredito da linha: maioria das 3 execuções; no empate, o mais severo (Não, Não sei, Sim). "
        "\"Sim\" quer dizer que o juiz concorda com a detecção do DAMFE."
    )
    out.append("")

    verdicts: dict[str, dict] = {}

    summary = ["| juiz | Sim | Não | Não sei | unânimes nas 3 execuções | κ de Cohen entre as 3 |", "|---|---|---|---|---|---|"]
    by_pattern: dict[str, dict] = {}

    for judge in JUDGES:

        items = load(judge)

        final = {key: majority(list(item["votes"].values())) for key, item in items.items()}
        verdicts[judge] = final

        counts = collections.Counter(final.values())
        total = len(final)

        complete = [
            [item["votes"][execution] for execution in EXECUTIONS]
            for item in items.values()
            if all(item["votes"].get(execution) in JUDGMENTS for execution in EXECUTIONS)
        ]
        unanimous = sum(1 for row in complete if len(set(row)) == 1)

        summary.append(
            f"| {judge} | {share(counts['Sim'], total)} | {counts['Não']} | {counts['Não sei']} "
            f"| {unanimous} de {len(complete)} ({unanimous / len(complete):.0%}) | {light(complete):.2f} |"
        )

        for key, item in items.items():
            by_pattern.setdefault(item["anti_pattern"], {}).setdefault(judge, collections.Counter())[final[key]] += 1

    out += ["## Por juiz", "", *summary, ""]

    out += [
        "## Concordância com o DAMFE, por anti-padrão",
        "",
        "Das detecções de cada anti-padrão, a parte em que o juiz respondeu Sim (concorda que é o anti-padrão), "
        "pelo veredito da linha. Ex.: das 35 de nano-frontend, a luna concordou com 4 (11%). Com 1 ou 2 detecções, o percentual não permite concluir nada.",
        "",
    ]
    header = "| anti-padrão | detecções | " + " | ".join(JUDGES) + " |"
    out += [header, "|" + "---|" * (len(JUDGES) + 2)]

    for pattern in sorted(by_pattern):
        rows = by_pattern[pattern]
        total = sum(rows[JUDGES[0]].values())
        out.append(f"| {pattern} | {total} | " + " | ".join(f"{rows[judge]['Sim']} ({rows[judge]['Sim'] / total:.0%})" for judge in JUDGES) + " |")

    out += ["", "## Entre os juízes", "", "| par | mesmo veredito | κ de Cohen |", "|---|---|---|"]

    for first, second in itertools.combinations(JUDGES, 2):
        keys = sorted(set(verdicts[first]) & set(verdicts[second]))
        table = [[verdicts[first][key], verdicts[second][key]] for key in keys
                 if verdicts[first][key] in JUDGMENTS and verdicts[second][key] in JUDGMENTS]
        same = sum(1 for a, b in table if a == b)
        out.append(f"| {first} × {second} | {same} de {len(table)} ({same / len(table):.0%}) | {cohen([tuple(row) for row in table]):.2f} |")

    out.append("")

    # Só o trecho entre os marcadores é gerado; a análise escrita à mão,
    # depois dele, fica como está.
    target = HERE / "resultados.md"
    generated = "\n".join([BEGIN, *out, END])
    current = target.read_text(encoding="utf-8") if target.is_file() else ""

    if BEGIN in current and END in current:
        before, rest = current.split(BEGIN, 1)
        after = rest.split(END, 1)[1]
        target.write_text(before + generated + after, encoding="utf-8")
    else:
        target.write_text(generated + "\n", encoding="utf-8")
    print("resultados.md")


if __name__ == "__main__":
    main()
