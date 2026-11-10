# MSR_MFE_Organizations

Mining study for identifying **real micro frontend systems** on GitHub, carried out for a master's dissertation at UFAM/ICOMP. It supports the evaluation of DAMFE, a static-analysis tool that reconstructs micro frontend architectures and detects anti-patterns.

The question the study answers is narrow and practical: *which micro frontend systems on GitHub are real enough to evaluate a tool against?*

## What is here

| | |
|---|---|
| [PROTOCOL.md](PROTOCOL.md) | the protocol as it stands, every decision taken on it, and the evidence behind each one |
| [EVALUATION.md](EVALUATION.md) | the plan for the expert evaluation of DAMFE's anti-pattern heuristics (working draft, in Portuguese) |
| [collect_repositories.py](collect_repositories.py) | the collection and automated screening, reproducible from the command line |
| [RUN-2026-09-24.md](RUN-2026-09-24.md) | the report of the run whose output feeds the manual assessment |
| [selection-flow.mmd](selection-flow.mmd) | the selection flow as a diagram, with what survived and what was discarded at each stage |
| [results/](results/) | the output of that run |
| [mineracao.log](mineracao.log) | the raw log of the run, kept as a record |

## Results

| file | rows | what it is |
|---|---|---|
| `results/raw.csv` | 20,099 | everything the search returned, excluded rows included, with the criterion and the term that fired |
| `results/screened.csv` | 1,907 | survivors of the automated screening |
| `results/siblings.csv` | 12,801 | every repository of each surviving organisation, for reassembling multi-repo systems |
| `results/organizations.csv` | 31 | the candidate organisations and the manual verdict on each |
| `results/summary.txt` | — | counts at each stage |

Nothing is deleted: a repository excluded automatically is a marked row in `raw.csv`, so one dropped by mistake stays recoverable.

**Where it ended up:** 20,099 repositories collected, 1,907 surviving the automated screening, 31 candidate organisations, and **14 systems included, holding 283 micro frontend repositories**. By integration technology: 207 single-spa, 58 with no framework (route-level composition), 10 mixed, 8 Module Federation.

## Reproducing it

```bash
export GITHUB_TOKEN=...
python3 collect_repositories.py \
    --min-commits 20 --min-lifespan-days 7 \
    --min-source-files 10 --siblings \
    --output results
```

Every output file carries, in its header, the collection timestamp, the executed query, the ordering, the window, which cuts were active and the request count. The same query run on a different day returns a different population, so these are not decoration — they are what makes a reported number checkable.

The criteria, their operationalisation and the evidence for every threshold are in [PROTOCOL.md](PROTOCOL.md).
