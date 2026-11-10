# Repository selection protocol

Living document. The protocol as it stands, the decisions taken on it, and the evidence behind each one. Implemented by [`collect_repositories.py`](collect_repositories.py).

Last updated: 04/10/2026.

---

## 1. Protocol

**Source**: GitHub.

**Search strategy**

Every term is quoted so that it matches a phrase ([D1](#d1--quoting-the-hyphenated-term)):

```
"micro frontend" OR microfrontend OR "micro frontends" OR "micro-frontend"
```

Creation window from 2008-01-01 to today — GitHub's own founding, so the window excludes nothing ([D2](#d2--creation-window-is-githubs-founding)) — and `sort:stars` on every query ([D3](#d3--ordering-by-sortstars)).

The search uses the **GraphQL API**: one query returns the repository and every signal at once. Pagination is by cursor; when a slice exceeds the 1000 results GitHub returns per query, the creation window is halved and each half restarts, so the cap truncates nothing silently. The file tree, used by EC7, is the only part on **REST** (`/repos/{owner}/{repo}/git/trees/HEAD?recursive=1`), because GraphQL returns one level per query.

**Unit of selection**: the **system**, not the repository. A system may span several repositories under one organisation ([D11](#d11--a-system-may-span-repositories)).

**Criteria**

| | criterion | layer | rule | automatic? |
|---|---|---|---|---|
| IC1 | It is a software implementation | 1 | `isEmpty`, or no language detected | yes |
| IC2 | It is a micro frontend system — one repository or one organisation — holding two or more micro frontends | 5 | two or more micro frontends counted by hand, in one repository or across one organisation ([D14](#d14--ic2-is-the-system-criterion)) | **manual**, narrowed |
| EC1 | Not a software implementation, or not a micro frontend system with two or more micro frontends | 1, 2, 5 | `isEmpty`, no language detected, or `micro` + a word from another domain with no mention of micro frontends ([D7](#d7--microservices-without-micro-frontends)) | yes, audited |
| EC5 | Forks of repositories already included | 1 | `isFork` | yes |
| EC3 | Boilerplates | 1, 2 | `isTemplate`, and the term *boilerplate* | yes, audited |
| EC2 | Examples or POCs, not real implementations | 2 | term of example or proof of concept in name, description or topics | yes, audited |
| EC4 | Frameworks, libraries or components | — | none | **manual** |
| EC6 | Abandoned on creation — nobody came back | 3 | ≥ 20 commits and ≥ 7 days between creation and last push ([D5](#d5--ec6-abandoned-on-creation)) | yes |
| EC7 | Too small to be a unit | 4 | ≥ 10 source files ([D12](#d12--ec7-redefined-as-a-unit-floor)) | yes |

Layers 1 to 4 screen **repositories**; layer 5 selects **systems**, and a system is one repository or one organisation ([D11](#d11--a-system-may-span-repositories)).

IC2 is decided by hand. Layer 5 does not test it — it only **narrows the field**, keeping owners that are organisations with two or more surviving repositories, so that there is a short list to read. The narrowing is coarser than the criterion, and what it misses is recorded in [D14](#d14--ic2-is-the-system-criterion).

**Layer 2 terms**

Matched in **name**, **description** and **topics**, always recording which term fired and in which field.

Covering EC2: example · examples · exemplo · exemplos · poc · proof-of-concept · proof of concept · tutorial · tutorials · hello-world · helloworld

Covering EC3: boilerplate

Covering EC1: microservi* · microfinan* · microbrew — undone when the text also mentions micro frontends, because a system with microservices behind and micro frontends in front is common.

**Why IC2 and EC4 have no automatic rule**

No API field tells an application from a library, or confirms a micro frontend architecture. The layer-5 rule is a proxy for IC2, never a decision: it narrows the field to organisations worth looking at, and the verdict is still made by hand. Detecting the technology through declared dependencies was tried and rejected ([D4](#d4--framework-filter-dropped)).

**Selection strategy**

The automatic screening runs in this order:

```
1. SEARCH    GraphQL: string + window + sort:stars
             paginate by cursor, halve the window past 1000

2. LAYER 1   isFork · isTemplate · isEmpty · no language

3. LAYER 2   term of example, POC, boilerplate, or another
             "micro" domain — records WHICH term and WHERE

4. LAYER 3   EC6: ≥ 20 commits and ≥ 7 days

5. PROBE     REST, one call per survivor: counts source
             files and package.json

6. LAYER 4   EC7: ≥ 10 source files

7. SIBLINGS  every public repository of each surviving
             organisation, so multi-repo systems can be
             reassembled

8. LAYER 5   narrows for IC2: owner is an organisation
             holding two or more surviving repositories

9. OUTPUT    sort by name, write the files
```

The cheap layers come before the probe, which costs one request per repository.

The remaining steps are manual: assess every candidate against the criteria and, if too many remain, compute a sample size and draw systems at random.

**Output**

| file | content |
|---|---|
| `raw.csv` | **everything**, excluded rows included, with criterion and reason |
| `screened.csv` | survivors, with blank columns for the manual assessment |
| `siblings.csv` | every repository of each surviving organisation, to be grouped by hand |
| `summary.txt` | counts at each stage, for the method write-up |

Nothing is deleted: an automatic exclusion becomes a marked row in `raw.csv`, so a serious repository dropped by mistake stays recoverable.

Two further files are written by hand, downstream of the script, and carry the decisions the script cannot make:

| file | content |
|---|---|
| `organizations.csv` | the 31 candidate organisations: the verdict on each (`included`), how many micro frontend repositories it holds, the name prefix that finds the rest of its units, the integration technology with the evidence for it, and a free note |
| `selection-flow.mmd` | the selection flow as a diagram, with what survived and what was discarded at each stage |

The `note` column of `organizations.csv` is the rater's own prose and stays in Portuguese; every column name and every controlled value is in English, as in the files the script writes.

**Data extraction**: DAMFE, plus manual detection following MIAPI.

---

## 2. Decisions

### D1 · Quoting the hyphenated term

The string now carries `"micro-frontend"` in quotes. GitHub treats a hyphen as a token separator, so unquoted the term degrades into "micro AND frontend anywhere in the record".

Measured over the whole corpus: 21,503 unquoted, 20,061 quoted. The 1,442 difference is noise, and **all five** pre-2014 hits came from it — a Backbone frontend for a *micro* incident system, a 2.3KB *micro* framework, the site of the Micro*brew*.it community. In the two-month pilot the 49 dropped were **microservice** frontends: `FoodPanda-Microservices-Frontend`, `OnlineStoreMicroservicesFrontend`, a Microsoft website clone.

Report the executed string, not the intended one.

### D2 · Creation window is GitHub's founding

`--since` defaults to 2008-01-01. The `created:` window exists only to beat the 1000-result cap; it is not a criterion. A default of 2014 imposed one the protocol never stated, and a mistargeted one at that, since it filters on when a repository was created rather than when it adopted micro frontends.

### D3 · Ordering by `sort:stars`

Without ordering GitHub uses relevance, which can reshuffle between pages and lose an item silently.

No key is immutable during a collection; stars is the slowest of the four available to move, not a guarantee. `sort:created` **does not exist** — GitHub ignores it without complaint and returns relevance order.

Verified: with and without ordering the collected sets are identical (608 = 608). The real defence is the `reported` ≠ `collected` warning in `collect()`.

### D4 · Framework filter dropped

Filtering by declared dependency was rejected. The original reason was that many implementations are hand-rolled. A probe of 108 repositories confirmed it for a stronger reason: only **8%** declare a known framework anywhere, while **38%** have no `package.json` at the root at all, because each micro frontend carries its own inside a subdirectory. Probing the root looks in the wrong place.

### D5 · EC6, abandoned on creation

Threshold: ≥ 20 commits and ≥ 7 days of lifespan.

EC2 excludes POCs but does not say how to recognise one. The keyword filter only catches what announces itself: it removed 19% of the base, while **64% of the survivors had a lifespan of a single day** — created and abandoned in one sitting.

Lifespan comes first and does the coarse work:

| commits | days | remaining | discards |
|---|---|---|---|
| ≥2 | 0 | 356 | 21% |
| ≥2 | 7 | 120 | 73% |

The commit count then cuts deep without costing anything identifiable. Among the 92 that survive a 7-day lifespan and EC7, the median is 14 commits, while every repository that reads as a real system on inspection sits far above it — 23, 40, 71, 92, 158, 165, 301 and 885:

| ≥ commits | remaining | discards | kills a plausible one? |
|---|---|---|---|
| 5 | 75 | 18% | no |
| 10 | 55 | 40% | no |
| **20** | **36** | **61%** | **no** |
| 30 | 18 | 80% | yes — `Drinkfy`, 23 commits |

Twenty leaves margin: the lowest plausible system has 23.

**Known bias**: both halves measure visible history. A repository published as a single squashed snapshot of long internal work has neither the commits nor the lifespan, and that is the profile of a real corporate system. The eight repositories used to check the threshold were judged by eye, not by ground truth, so 20 is defensible rather than proven.

### D6 · EC7, first version — superseded

The first version of EC7 cut on source files **and** on the number of `package.json` files, with a threshold set for a whole system. Superseded by [D12](#d12--ec7-redefined-as-a-unit-floor).

### D7 · Microservices without micro frontends

Implemented in layer 2, as an automatic rule for **EC1** — a microservice frontend does not implement micro frontends. It is not a criterion of its own. Excludes anything mentioning microservices, microfinance or microbrewing **and not** micro frontends.

The search requires the words "micro" and "frontend", not the subject, and a microservice frontend is the commonest collision: eleven of the 108 pilot survivors, twenty-four across two months. Mentioning micro frontends undoes the exclusion, because a system with microservices behind and micro frontends in front would otherwise be the one discarded.

### D13 · Where each threshold comes from

Every number in the criteria table was chosen against measured data, never decreed. This entry gathers them so the reasoning survives the next revision.

| threshold | value | what fixes it |
|---|---|---|
| EC6, lifespan | 7 days | 64% of what survives layer 2 lives a single day. Seven days is the shortest window that separates "came back to it" from "wrote it in one sitting" |
| EC6, commits | 20 | the median of the survivors is 14; every repository that reads as a real system sits at 23 or above. Twenty is the highest value that kills none of them |
| EC7, source files | 10 | the smallest unit of a real system, `healthcare-system`, holds 13. Ten leaves margin below the floor of a unit |
| layer 2 terms | 11 of 34 | a term qualifies only when it cannot describe anything but the repository itself ([D10](#d10--recall-over-precision-in-layer-2)) |

Three of the four rest on judging by eye which repositories look real, over one two-month pilot. They are defensible, not proven, and nothing in the current design calibrates them against ground truth.

### D8 · Signals rejected

| signal | catches | why not |
|---|---|---|
| no topics | 95% | does not discriminate |
| 0 stars and 0 forks | 92% | biased against corporate code |
| no description | 61% | same |
| no web language | 0.5% | GitHub always finds JavaScript or HTML |
| CI, Docker, tests | 36% / 10% / 36% | measures engineering practice, not whether the thing is real; modern scaffolds ship a workflow, and `micro-frontend-practise-2` has one |
| third-party issues, forks, releases | 25% | measures visibility, not reality; a corporate system published without fanfare has none of it, and that is the profile most wanted |

### D9 · Topic search removed

The search is the string alone. The eight micro frontend topics repeat the words the string already matches, so keeping nine queries was near-duplicate work.

**Caveat**: the overlap was assumed, not measured. If the dissertation needs to claim nothing was lost, run the topic queries once over a short window and report how many repositories only they bring.

### D10 · Recall over precision in layer 2

Layer 2 kept 11 terms. A term only qualifies when it cannot describe anything but the repository itself.

The two errors do not cost the same. A repository wrongly kept costs a rater a few minutes. A repository wrongly discarded is **invisible** — it reaches nobody who could notice, and leaves the sample without a trace. In a selection whose targets are already rare, the second error is the expensive one.

Removed for describing the product's subject: `course`, `curso`, `study`, `estudo`, `learning`, `teaching`, `training`, `exercise`, `exercicio`, `seed`, `generator`, `template`, `experiment`, `workshop`. An education platform writes "course" for reasons that have nothing to do with being a course.

Removed for naming things real products have: `demo`, `sample`, `playground`, `sandbox`, `starter`, `scaffold`, `scaffolding`, `skeleton`.

Cost: exclusions fell from 81 to 54 in the pilot. Evidence: 30 repositories had been excluded **only** by an ambiguous term, among them `kobevino/mfa-template`, with 260 commits over 271 days, dropped for having "template" in its name.

### D11 · A system may span repositories

The unit of selection is the **system**. A system may be one repository or several, under one organisation.

The consequence forces a new step: the units of a multi-repo system **do not all match the search string**. A repository named `mfe-checkout` may never write "micro frontend" anywhere, and grouping the search's own results by owner inherits that truncation — the system enters with two units out of seven. So `--siblings` lists **every** public repository of each surviving owner, and the grouping happens by hand in `siblings.csv`.

**Organisations only.** A personal account holds whatever its owner ever wrote: in the pilot, 21 accounts held 615 repositories for the 23 that had matched. With the filter, 49 owners became 3 organisations and 30 rows. A system split across repositories is something a team does, and a team has an organisation.

**Effect on sampling**: raters judge systems, and step 4 draws systems.

### D12 · EC7 redefined as a unit floor

The size cut stays, counting **source files**, with the threshold at the floor of a **unit** rather than of a system: **10**. The `package.json` count is gone.

The earlier version assumed repository = system, and [D11](#d11--a-system-may-span-repositories) decided otherwise. With multi-repo systems a repository is a unit, and a unit is small by design — that is the point of the architecture.

Evidence: the seven units of `healthcare-system`, a real system, hold between 13 and 28 source files and **one** `package.json` each. The earlier cut, at ≥50 files and ≥2 packages, would have discarded all seven. Counting `package.json` is the same mistake in sharper form: a unit has exactly one.

| ≥ source files | remaining | discards |
|---|---|---|
| 8 | 97 | 10% |
| **10** | **92** | **15%** |
| 13 | 88 | 19% |
| 20 | 66 | 39% |

**Known bias**: the cut falls hardest on units of multi-repo systems, which are small precisely because they are units. In the pilot it discarded two pairs that together form a system — `micro-frontend-multi-zones-main-app` and `-blog-app`, from the same owner, with 6 and 9 files.

### D14 · IC2 is the system criterion

The inclusion criteria used to read as two statements about a repository: IC1, it is a software repository, and IC2, it implements one or more micro frontends. Neither said what the study actually selects, and IC1 restated what EC1 already excluded.

They are now one statement per level. **IC1** keeps the repository gate — it is a software implementation — and is the eligibility test for the raw material the search returns. **IC2** is the criterion for what the study includes: a micro frontend system holding **two or more** micro frontends, where the system is **one repository or one organisation**. It is decided by hand; layer 5 only narrows the field so that there is a short list to read. **EC1** is the negation of both, which is why it is the only criterion that acts at both levels.

Two or more, not one, because a single micro frontend has no architecture to reconstruct: there is no composition, no inter-unit communication and no dependency graph, so nothing the tool exists to find.

Either shape counts as a system, and the included set holds both: `sihsalus` and `fubaritico` are **monorepos**, one repository each holding several micro frontends, while `gematik` and `pagopa` are organisations with one repository per unit. A criterion that admitted only the second shape would have excluded two of the fourteen.

**Known limit, and it is the serious one.** The narrowing only ever reaches the organisation shape: layer 5 asks whether the owner is an `Organization` with two or more surviving repositories. **No step looks for a monorepo under a personal account**, and the owner filter discarded 1,463 of them on the 24/09 run. `sihsalus` and `fubaritico` entered through the organisation path and turned out to be monorepos once read by hand — not because anything searched for that shape. IC2 is therefore broader than what the narrowing reaches, and the gap is a threat to validity, not a criterion: a personal account holding a monorepo with five micro frontends satisfies IC2 and was never seen.

---

## 3. How to run

```bash
export GITHUB_TOKEN=...

# the protocol with no additions
python3 collect_repositories.py --output results

# with EC6 and EC7, and the sibling listing
python3 collect_repositories.py \
    --min-commits 2 --min-lifespan-days 7 \
    --min-source-files 10 --siblings \
    --output results

# a quick pilot, no probe
python3 collect_repositories.py \
    --since 2025-01-01 --until 2025-02-28 --no-probe \
    --output pilot
```

---

## 4. Reproducibility

Every output file carries the collection timestamp, the executed string, the ordering, the window, which cuts were active and the request count. The same query run on a different day returns a different population, so these are not decoration — they are the only thing that makes a reported number checkable.

A warning is printed whenever `repositoryCount` differs from what was collected. CSVs are sorted by name, because GitHub's relevance order is unstable between runs and two runs could not otherwise be diffed.

---

## 5. Where it stands

Two-month pilot (January–February 2025), with EC6 and EC7 on:

| | |
|---|---|
| collected | 608 |
| layer 1 — fork, template, empty | 89 |
| layer 2 — example, POC, boilerplate (55) and EC1 by another "micro" (24) | 79 |
| layer 3 — EC6, abandoned on creation | 335 |
| layer 4 — EC7, too small to be a unit | 14 |
| **for manual assessment** | **91** |

Those numbers come from a run with EC6 at 2 commits. With the thresholds now decided — 20 commits, 7 days, 10 source files — the same window leaves **37**.

Extrapolating to the full window: around 20,000 collected and **roughly 1,200 for manual assessment**.

**Open**: fire the full collection · decide whether a repository that cannot be a system at all — one unit, and an owner with no other repository — should be excluded, which would cut 25 of the 91 · assess IC2 and EC4 by hand.
