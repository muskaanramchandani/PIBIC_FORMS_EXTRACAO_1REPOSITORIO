"""
Precisão, revocação e matriz de confusão dos dois juízes.

Uso: python3 metricas.py

Reconstrução (agent-judge): precisão pela amostra da parte 1; revocação pelos
MFEs sorteados da parte 2 ("o que faltou"). Detecções (llm-judge): precisão
pelos vereditos; revocação pelas omissões conferidas. Veredito de cada item:
maioria das 3 execuções em cada juiz, depois maioria dos 3 juízes; no empate,
o mais severo. Sem nabstore e halloween, como nas outras análises.
"""

import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
AGENT = HERE.parent / "agent-judge"
LLM = HERE.parent / "llm-judge"
ARTIFACTS = HERE.parent / "reconstrucao-corrigida"
EXCLUDED = {"nabstore", "halloween"}

sys.path[:0] = [str(AGENT)]
import resultados as agent  # noqa: E402

sys.path[0] = str(LLM)
del sys.modules["resultados"]
import resultados as llm  # noqa: E402

AGENT_SEVERITY = ["incorreto", "parcial", "nao_verificavel", "correto"]


def consensus(votes: list[str], severity: list[str]) -> str:
    counts = collections.Counter(votes)
    top = max(counts.values())
    return next(verdict for verdict in severity if counts.get(verdict) == top)


def pct(part: float, whole: float) -> str:
    return f"{part / whole:.0%}" if whole else "—"


def reconstruction() -> list[str]:

    with (AGENT / "amostra.csv").open(encoding="utf-8") as handle:
        sample = {(row["sistema"], row["id"]): row for row in csv.DictReader(handle)}

    judges = {}
    for folder in sorted((AGENT / "runs").iterdir()):
        votes, _ = agent.load(folder)
        judges[folder.name] = {key: agent.majority(list(value.values())) for key, value in votes.items() if key in sample}

    precision = collections.defaultdict(collections.Counter)
    for key in sample:
        if key[0] in EXCLUDED:
            continue
        verdicts = [decided[key] for decided in judges.values() if key in decided]
        precision[sample[key]["tipo"]][consensus(verdicts, AGENT_SEVERITY)] += 1

    # População por tipo (itens extraídos), para pesar a precisão total.
    population = collections.Counter()
    for system in ARTIFACTS.iterdir():
        if system.is_dir() and system.name not in EXCLUDED:
            population.update(count_all(system.name))

    # Revocação: itens extraídos dos MFEs sorteados e falsos negativos conferidos.
    drawn = []
    for name in ("amostra.csv", "amostra-udistrital.csv"):
        with (AGENT / "faltou" / name).open(encoding="utf-8") as handle:
            drawn += list(csv.DictReader(handle))
    extracted = collections.Counter()
    for row in drawn:
        extracted.update(count_unit(row["sistema"], row["mfe"], row["diretorio"]))

    with (AGENT / "faltou" / "conferencia.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["final"] == "falso negativo"]
    missing = collections.Counter()
    for item in {row["item"]: row for row in rows}.values():
        missing[item["tipo"]] += 1

    types = ["micro frontend", "tela", "fragmento", "composição", "navegação", "comunicação", "chamada de API", "acesso a estado"]
    out = ["RECONSTRUÇÃO", "tipo | N | amostra | correto | parcial | incorreto | não verif. | precisão estrita | precisão com parcial | extraídos nos MFEs sorteados | FN | revocação"]
    totals = collections.Counter()
    weighted = [0.0, 0.0, 0]
    for kind in types:
        c = precision[kind]
        judged = c["correto"] + c["parcial"] + c["incorreto"]
        e, f = extracted[kind], missing[kind]
        out.append(f"{kind} | {population[kind]} | {sum(c.values())} | {c['correto']} | {c['parcial']} | {c['incorreto']} | "
                   f"{c['nao_verificavel']} | {pct(c['correto'], judged)} | {pct(c['correto'] + c['parcial'], judged)} | "
                   f"{e} | {f} | {pct(e, e + f)}")
        totals.update(c)
        totals["E"] += e
        totals["F"] += f
        if judged:
            weighted[0] += population[kind] * c["correto"] / judged
            weighted[1] += population[kind] * (c["correto"] + c["parcial"]) / judged
            weighted[2] += population[kind]
    judged = totals["correto"] + totals["parcial"] + totals["incorreto"]
    out.append(f"total (amostra) | {sum(population.values())} | {judged + totals['nao_verificavel']} | {totals['correto']} | {totals['parcial']} | "
               f"{totals['incorreto']} | {totals['nao_verificavel']} | {pct(totals['correto'], judged)} | "
               f"{pct(totals['correto'] + totals['parcial'], judged)} | {totals['E']} | {totals['F']} | {pct(totals['E'], totals['E'] + totals['F'])}")
    out.append(f"total pesado pela população | precisão estrita {weighted[0] / weighted[2]:.0%} | com parcial {weighted[1] / weighted[2]:.0%}")
    out.append(f"MFEs sorteados: {len(drawn)}")
    return out


def count_unit(system: str, mfe: str, directory: str) -> collections.Counter:
    load = lambda name: json.loads((ARTIFACTS / system / f"{name}.json").read_text(encoding="utf-8"))
    unit = next(u for u in load("microfrontends") if u["id"] == mfe and (not directory or u.get("directory") == directory))
    c = collections.Counter()
    c["micro frontend"] = 1
    c["tela"] = len(unit.get("screens") or [])
    c["fragmento"] = len(unit.get("fragments") or [])
    c["composição"] = sum(mfe in (i["consumer"], i["provider"]) for i in load("compositions"))
    c["navegação"] = sum(mfe in (i["source"], i["target"]) for i in load("navigations"))
    c["comunicação"] = sum(mfe in (i["source"], i["target"]) and i.get("directed", True) for i in load("communications"))
    c["chamada de API"] = sum(i["microfrontend"] == mfe for i in load("api_calls"))
    c["acesso a estado"] = sum(i["microfrontend"] == mfe for i in load("state_accesses"))
    return c


def count_all(system: str) -> collections.Counter:
    load = lambda name: json.loads((ARTIFACTS / system / f"{name}.json").read_text(encoding="utf-8"))
    units = load("microfrontends")
    c = collections.Counter()
    c["micro frontend"] = len(units)
    c["tela"] = sum(len(u.get("screens") or []) for u in units)
    c["fragmento"] = sum(len(u.get("fragments") or []) for u in units)
    c["composição"] = len(load("compositions"))
    c["navegação"] = len(load("navigations"))
    c["comunicação"] = sum(1 for i in load("communications") if i.get("directed", True))
    c["chamada de API"] = len(load("api_calls"))
    c["acesso a estado"] = len(load("state_accesses"))
    return c


def detections() -> list[str]:

    per_judge = {judge: llm.load(judge) for judge in llm.JUDGES}
    keys = set.intersection(*(set(items) for items in per_judge.values()))
    table = collections.defaultdict(collections.Counter)
    for key in keys:
        verdicts = [llm.majority(list(per_judge[j][key]["votes"].values())) for j in llm.JUDGES]
        table[per_judge[llm.JUDGES[0]][key]["anti_pattern"]][consensus(verdicts, llm.SEVERITY)] += 1

    missing = {"nano-frontend": 4}
    out = ["DETECÇÕES", "anti-padrão | detecções | Sim (VP) | Não (FP) | Não sei | FN conferidos | precisão | revocação"]
    total = collections.Counter()
    for name in sorted(table):
        c = table[name]
        f = missing.get(name, 0)
        out.append(f"{name} | {sum(c.values())} | {c['Sim']} | {c['Não']} | {c['Não sei']} | {f} | "
                   f"{pct(c['Sim'], c['Sim'] + c['Não'])} | {pct(c['Sim'], c['Sim'] + f)}")
        total.update(c)
        total["F"] += f
    out.append(f"total | {sum(table[n].total() for n in table)} | {total['Sim']} | {total['Não']} | {total['Não sei']} | {total['F']} | "
               f"{pct(total['Sim'], total['Sim'] + total['Não'])} | {pct(total['Sim'], total['Sim'] + total['F'])}")
    return out


if __name__ == "__main__":
    print("\n".join(reconstruction() + [""] + detections()))
