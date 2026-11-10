"""
Resume os vereditos do agent as a judge.

Uso: python3 resultados.py

Lê `runs/<modelo>/` e escreve `resultados.md`: por modelo, a precisão por
tipo e por sistema (pela maioria das execuções, quando há mais de uma), a
concordância entre as execuções do mesmo modelo e a concordância entre os
modelos, item a item. 
"""

import collections
import csv
import itertools
import json
from pathlib import Path

BEGIN = "<!-- início do trecho gerado por resultados.py -->"
END = "<!-- fim do trecho gerado -->"
HERE = Path(__file__).parent
VERDICTS = ["correto", "parcial", "incorreto", "nao_verificavel"]


def share(hits: int, total: int) -> str:

    return f"{hits / total:.0%}" if total else "—"


def majority(votes: list[str]) -> str:
    """O veredito mais votado; no empate, o mais severo dos empatados."""

    counts = collections.Counter(votes)
    top = max(counts.values())
    severity = ["incorreto", "parcial", "correto", "nao_verificavel"]

    return next(verdict for verdict in severity if counts.get(verdict) == top)


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


def load(folder: Path) -> tuple[dict, dict]:
    """Os votos por item, por execução, e o modelo e o provedor de cada sessão."""

    votes: dict[tuple, dict[int, str]] = collections.defaultdict(dict)
    served = collections.Counter()

    for file in folder.glob("*/execucao-*.json"):

        record = json.loads(file.read_text())

        if not record.get("ok"):
            continue

        served[(record.get("model"), record.get("provider"))] += 1

        for key in record["items"]:
            votes[(record["system"], key)][record["execution"]] = record["verdicts"][key]["veredito"]

    return votes, served


def main() -> None:

    with (HERE / "amostra.csv").open(encoding="utf-8") as handle:
        sample = {(row["sistema"], row["id"]): row for row in csv.DictReader(handle)}

    models = {folder.name: load(folder) for folder in sorted((HERE / "runs").iterdir()) if folder.is_dir()}
    models = {name: found for name, found in models.items() if found[0]}
    out = ["# Agent as a judge — resultados", ""]
    final: dict[str, dict] = {}

    for name, (votes, served) in models.items():

        complete = {key: value for key, value in votes.items() if key in sample}
        executions = max((len(value) for value in complete.values()), default=0)
        decided = {key: majority(list(value.values())) for key, value in complete.items()}
        final[name] = decided

        out += [f"## {name}", ""]
        out += [f"- itens com veredito: **{len(decided)} de {len(sample)}**; execuções por item: "
                + ", ".join(f"{n} → {c}" for n, c in sorted(collections.Counter(len(v) for v in complete.values()).items()))]
        out += ["- sessões atendidas por: " + "; ".join(f"{model} via {provider} ({count})"
                                                       for (model, provider), count in served.most_common())]
        out += ["- veredito do item: " + ("maioria das execuções" if executions > 1 else "uma execução"), ""]

        for label, group in (("tipo", lambda key: sample[key]["tipo"]), ("sistema", lambda key: key[0])):

            out += [f"| {label} | itens | correto | parcial | incorreto | não verificável |", "|---|---|---|---|---|---|"]
            buckets = collections.defaultdict(collections.Counter)
            for key, verdict in decided.items():
                buckets[group(key)][verdict] += 1
            total = collections.Counter()
            for bucket, counts in sorted(buckets.items()):
                total += counts
                size = sum(counts.values())
                out.append(f"| {bucket} | {size} | {share(counts['correto'], size)} | {counts['parcial']} | "
                           f"{counts['incorreto']} | {counts['nao_verificavel']} |")
            size = sum(total.values())
            out += [f"| **total** | **{size}** | **{share(total['correto'], size)}** | {total['parcial']} | "
                    f"{total['incorreto']} | {total['nao_verificavel']} |", ""]

        triple = [[value[n] for n in sorted(value)] for value in complete.values() if len(value) == 3]

        if triple:
            unanimous = sum(len(set(row)) == 1 for row in triple)
            out += ["**Estabilidade entre as 3 execuções**", "",
                    f"- itens com as 3: {len(triple)}; unânimes: {unanimous} ({unanimous / len(triple):.0%})",
                    f"- kappa de Cohen (média dos 3 pares): {light(triple):.2f}", ""]

    if len(final) > 1:

        names = list(final)
        out += ["## Entre os modelos", ""]

        for index, first in enumerate(names):
            for second in names[index + 1:]:
                shared = sorted(set(final[first]) & set(final[second]))
                pairs = [[final[first][key], final[second][key]] for key in shared]
                same = sum(a == b for a, b in pairs)
                out += [f"**{first} × {second}**: {len(shared)} itens em comum; mesmo veredito em {same} "
                        f"({same / len(shared):.0%}); kappa de Cohen {cohen([tuple(row) for row in pairs]):.2f}" if shared else
                        f"**{first} × {second}**: nenhum item em comum", ""]

                differ = collections.Counter((a, b) for a, b in pairs if a != b)
                if differ:
                    out += [f"| {first} | {second} | itens |", "|---|---|---|"]
                    out += [f"| {a} | {b} | {count} |" for (a, b), count in differ.most_common()]
                    out.append("")

    # Só o trecho entre os marcadores é gerado; o que vem depois, escrito
    # à mão, fica como está.
    target = HERE / "resultados.md"
    generated = "\n".join([BEGIN, *out, END])
    current = target.read_text(encoding="utf-8") if target.is_file() else ""

    if BEGIN in current and END in current:
        before, rest = current.split(BEGIN, 1)
        target.write_text(before + generated + rest.split(END, 1)[1], encoding="utf-8")
    else:
        target.write_text(generated + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
