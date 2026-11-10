#!/usr/bin/env python3
"""
Repository mining and automated screening for the DAMFE evaluation.

This script implements the mechanical part of the selection protocol
reproduced below. It queries the GitHub GraphQL API, applies the
criteria that can be decided without judgement, and gathers the
evidence the manual assessment needs.

It deliberately does NOT decide whether a repository implements micro
frontends, whether it is a real implementation, or whether it is a
framework. Those are judgement calls and belong to the raters. What
the script guarantees is that every rater looks at the same evidence,
which is what makes their agreement mean anything.


===========================================================================
THE PROTOCOL
===========================================================================

Translated from the original Portuguese. The search string is verbatim.

    Source: GitHub

    Search strategy: start from the search string, then a first pass
    filtered by topic.

      1. Search string:
         "micro frontend" OR microfrontend OR "micro frontends"
         OR "micro-frontend"

         Every term is quoted so that it matches a phrase. See
         SEARCH_STRING for why the last one must be.

      2. Topic queries were dropped. An earlier draft also collected
         every repository under eight micro frontend topics; the
         search string already matches the same words, so they were
         removed rather than kept as near-duplicate work.

    Inclusion criteria (AND):

      IC1. It is a software implementation
      IC2. It is a Micro Frontend system — one repository or one
           organisation — holding two or more Micro Frontends

    Exclusion criteria:

      EC1. Not a software implementation, or not a Micro Frontend
           system with two or more Micro Frontends
      EC2. Examples or POC implementations rather than real Micro
           Frontend implementations
      EC3. Boilerplates for creating Micro Frontends
      EC4. Frameworks, libraries or components for Micro Frontends
      EC5. Forks of repositories already included

    The repository is the unit of FILTERING: everything the search
    returns is screened there. The system is the unit of SELECTION,
    and it is one repository or one organisation — a monorepo holding
    several Micro Frontends is a system just as an organisation with
    one repository per unit is.

    Selection strategy:
      (1) Clean the base by removing repositories per the exclusion
          criteria
      (2) Manually assess every repository against the inclusion and
          exclusion criteria
      (3) If too many remain, compute an adequate sample size and
          draw randomly from them

    Data extraction: run DAMFE, plus manual detection following MIAPI.


===========================================================================
HOW EACH CRITERION IS OPERATIONALISED
===========================================================================

Ordered by layer. Inclusion first, then exclusion.

    criterion  layer  rule                                automatic
    ---------  -----  ----------------------------------  ---------
    IC1        1      isEmpty, or no language detected    yes
    IC2        5      two or more Micro Frontends,        manual,
                      counted by hand                     narrowed
    EC1        1, 2   same as IC1, and another "micro"    yes
                      domain; at system level, not IC2
    EC5        1      isFork flag                         yes
    EC3        1, 2   isTemplate flag, and the term       yes,
                      boilerplate                         audited
    EC2        2      term of example or proof of         yes,
                      concept in name, description        audited
                      or topics
    EC6        3      abandoned on creation: commits      yes
                      and days between creation and
                      last push
    EC7        4      no mass of code: source-file and    yes
                      package.json counts
    EC4        —      none                                manual

Layer 5 does not test IC2. It only NARROWS the field, keeping owners
that are organisations with two or more surviving repositories, so
that there is a short list to read; the verdict is made by hand. The
narrowing is coarser than the criterion — nothing here looks for a
monorepo under a personal account.

IC2 and EC4 have no automatic rule on purpose. Detecting the micro
frontend technology through declared dependencies was considered and
rejected: only 8% of a 108-repository probe declared a known framework
anywhere, while 38% had no package.json at the root at all, because in
this architecture each micro frontend carries its own inside a
subdirectory.

The archived flag does NOT exclude. A real system that was
discontinued is still a real system; the flag is recorded as a signal.


===========================================================================
REPRODUCIBILITY
===========================================================================

GitHub's search caps at 1000 results per query no matter how many
exist. Queries that exceed it are split by creation date until each
slice fits, so nothing is dropped silently.

That date window is a pagination device and nothing more. It is NOT
one of the protocol's criteria, and narrowing it would quietly add one
the protocol never stated — worse, a mistargeted one, since it filters
on when a repository was created rather than when it adopted micro
frontends. A codebase started in 2011 that moved to module federation
in 2022 is precisely the kind of real system this study wants, so the
window defaults to GitHub's own beginning.

Every output file carries the collection timestamp, the exact queries
issued and the API request count in its header. The
same query run on a different day returns a different population, so
these are not decoration — they are the only thing that makes a
reported result checkable.


Usage:

    export GITHUB_TOKEN=ghp_...
    python3 collect_repositories.py --output results/

Outputs:

    raw.csv             every repository the queries returned
    screened.csv        survivors of layers 1 and 2, for manual review
    summary.txt         counts at each stage, for the method write-up
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


ENDPOINT = "https://api.github.com/graphql"

#: Protocol, step 1. Verbatim.
#:
#: The last term is quoted deliberately. GitHub treats a hyphen as a
#: token separator, so a bare `micro-frontend` degrades into "micro
#: AND frontend anywhere in the record" instead of the phrase. An
#: earlier draft of this protocol left it bare; the quotes are the
#: correction.
#:
#: Measured over the whole corpus: bare, 21,503 repositories; quoted,
#: 20,061. Those 1,442 are loose matches, and all five pre-2014 hits
#: came from them — a Backbone frontend for a "micro incident
#: management system", a 2.3KB "micro framework", the site of a
#: homebrewing community called Microbrew.it. None is a micro
#: frontend, and the term did not exist when they were written.
SEARCH_STRING = (
    '"micro frontend" OR microfrontend OR "micro frontends" '
    'OR "micro-frontend"'
)

#: Ordering applied to every query.
#:
#: The search has no ordering of its own — GitHub falls back to
#: relevance, which can reshuffle between one page and the next and
#: silently drop an item across a page boundary.
#:
#: Note that no stable key exists. Repository search sorts by stars,
#: forks, updated or help-wanted-issues, and every one of them can
#: change while a collection is running; `sort:created`, which would
#: be immutable, is NOT a valid qualifier — GitHub ignores it without
#: complaint and returns relevance order, so a run that believes it
#: sorted by creation date has sorted by nothing.
#:
#: Stars are the slowest of the four to move, which makes this the
#: least unstable option rather than a safe one. The real guarantee is
#: the reported-versus-collected check in collect().
SORT = "sort:stars"

SEARCH_CAP = 1000

#: Terms for layer 2, covering EC2 and EC3. Matched in name,
#: description and topics; the term and the field that matched are
#: recorded so a rater can overturn the call. Short on purpose — see
#: D10 in PROTOCOL.md.
EXCLUSION_TERMS = (
    # EC2 — examples and proofs of concept
    "example", "examples", "exemplo", "exemplos",
    "poc", "proof-of-concept", "proof of concept",
    "tutorial", "tutorials",
    "hello-world", "helloworld",
    # EC3 — boilerplates
    "boilerplate",
)

#: Palavras que grudam em "micro" e não têm nada com micro frontend.
#:
#: A busca casa `microfinance_frontend` e `FoodPanda-Microservices-
#: Frontend` porque as duas palavras aparecem; o assunto é outro. Este
#: é o critério D7.
OTHER_MICRO = re.compile(
    r"micro[\s_\-]?servi|micro[\s_\-]?finan|microbrew", re.I
)

#: O que desfaz a exclusão acima.
#:
#: Sistema com microsserviços no backend E micro frontends na
#: interface é comum, e a regra cega descartaria justamente ele.
IS_MICROFRONTEND = re.compile(
    r"micro[\s_\-]?front|mfe\b|module[\s_\-]?federation|single[\s_\-]?spa",
    re.I,
)




#: What counts as a source file when measuring a repository, and what
#: is skipped. Disk usage is NOT a usable measure of size here: a
#: lockfile alone runs to hundreds of kilobytes and a single
#: screenshot outweighs the whole of a small application. Counting
#: source files is what separates a system from a demonstration.
SOURCE_FILE = re.compile(r"\.(js|jsx|ts|tsx|vue|svelte|mjs|cjs)$", re.I)

#: Directories whose contents are not the repository's own code.
NOT_SOURCE = re.compile(
    r"(^|/)(node_modules|dist|build|\.next|out|coverage|vendor)/", re.I
)


OWNER_QUERY = """
query($login: String!, $cursor: String) {
  repositoryOwner(login: $login) {
    __typename
    repositories(
      first: 100
      after: $cursor
      privacy: PUBLIC
      isFork: false
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        url
        description
        isEmpty
        pushedAt
        primaryLanguage { name }
        repositoryTopics(first: 10) { nodes { topic { name } } }
      }
    }
  }
}
"""


QUERY = """
query($search: String!, $cursor: String) {
  search(query: $search, type: REPOSITORY, first: 25, after: $cursor) {
    repositoryCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Repository {
        nameWithOwner
        url
        description
        homepageUrl
        createdAt
        pushedAt
        isFork
        isArchived
        isTemplate
        isEmpty
        stargazerCount
        forkCount
        diskUsage
        primaryLanguage { name }
        languages(first: 10) { nodes { name } }
        repositoryTopics(first: 25) { nodes { topic { name } } }
        releases { totalCount }
        issues { totalCount }
        pullRequests { totalCount }
        watchers { totalCount }
        licenseInfo { key }
        defaultBranchRef {
          name
          target {
            ... on Commit {
              committedDate
              history(first: 1) { totalCount }
            }
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------


class Client:

    def __init__(self, token: str, pause: float = 1.0):
        self.token = token
        self.pause = pause
        self.requests = 0

    def run(self, search: str, cursor: str | None) -> dict:
        """
        One page of a search, retrying on transient failure.

        Rate limiting and API hiccups are routine over a long
        collection. Giving up on the first failure would waste hours
        and, worse, would produce a truncated population with no
        indication that anything was missed.

        GitHub's search endpoint returns 502 intermittently under no
        discernible pattern — the same query fails and then succeeds
        seconds later — so the retry budget is deliberately generous.
        """

        payload = json.dumps(
            {"query": QUERY, "variables": {"search": search, "cursor": cursor}}
        ).encode()

        for attempt in range(10):

            request = urllib.request.Request(
                ENDPOINT,
                data=payload,
                headers={
                    "Authorization": f"bearer {self.token}",
                    "Content-Type": "application/json",
                    "User-Agent": "damfe-study",
                },
            )

            try:
                body = json.load(urllib.request.urlopen(request, timeout=90))
            except urllib.error.HTTPError as error:
                delay = min(20 * (attempt + 1), 120)
                print(f"    HTTP {error.code} — retrying in {delay}s",
                      file=sys.stderr)
                time.sleep(delay)
                continue
            except Exception as error:
                delay = 15 * (attempt + 1)
                print(f"    {type(error).__name__} — retrying in {delay}s",
                      file=sys.stderr)
                time.sleep(delay)
                continue

            if "errors" in body:
                message = body["errors"][0].get("message", "")
                if "rate limit" in message.lower():
                    print("    rate limited — waiting 60s", file=sys.stderr)
                    time.sleep(60)
                    continue
                raise RuntimeError(message)

            self.requests += 1
            time.sleep(self.pause)

            return body["data"]["search"]

        raise RuntimeError("repeated API failures")

    def owned_by(self, login: str, limit: int = 300) -> list[dict]:
        """
        Every public, non-fork repository of one owner.

        A system split across repositories does not announce itself in
        each of them: a repository named `mfe-checkout` may never write
        "micro frontend" anywhere, and the search then finds two units
        of a system of seven. Grouping the search's own results by owner
        inherits that truncation, so the owner's repositories have to be
        listed rather than filtered.

        Only organisations are listed. A personal account holds
        whatever its owner ever wrote: 21 accounts in the pilot held
        615 repositories, 23 of which had matched, and grouping the
        other 592 by hand buys nothing. A system split across
        repositories is something a team does, and a team has an
        organisation.
        """

        found: list[dict] = []

        cursor = None

        while len(found) < limit:

            body = json.dumps(
                {
                    "query": OWNER_QUERY,
                    "variables": {"login": login, "cursor": cursor},
                }
            ).encode()

            request = urllib.request.Request(
                ENDPOINT,
                data=body,
                headers={
                    "Authorization": f"bearer {self.token}",
                    "Content-Type": "application/json",
                    "User-Agent": "damfe-study",
                },
            )

            try:
                answer = json.load(
                    urllib.request.urlopen(request, timeout=60)
                )
            except Exception:
                return found

            self.requests += 1

            owner = (answer.get("data") or {}).get("repositoryOwner")

            if not owner:
                return found

            if owner.get("__typename") != "Organization":
                return []

            page = owner["repositories"]

            found.extend(node for node in page["nodes"] if node)

            if not page["pageInfo"]["hasNextPage"]:
                break

            cursor = page["pageInfo"]["endCursor"]

            time.sleep(self.pause)

        return found

    def tree(self, repo: str) -> list[str] | None:
        """
        Every file path in a repository, in a single REST call.

        GraphQL cannot walk a tree recursively — it returns one level
        per query — so this is the one place the REST API is cheaper.
        Returns None when the tree cannot be read, which is a fact to
        record rather than a reason to exclude.
        """

        url = (
            f"https://api.github.com/repos/{repo}"
            "/git/trees/HEAD?recursive=1"
        )

        for attempt in range(4):

            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "damfe-study",
                },
            )

            try:
                body = json.load(urllib.request.urlopen(request, timeout=60))
            except urllib.error.HTTPError as error:
                if error.code in (404, 409):
                    return None
                time.sleep(10 * (attempt + 1))
                continue
            except Exception:
                time.sleep(10 * (attempt + 1))
                continue

            self.requests += 1

            return [
                entry["path"]
                for entry in body.get("tree", [])
                if entry.get("type") == "blob"
            ]

        return None


# ---------------------------------------------------------------------------
# Collection: pagination plus date slicing
# ---------------------------------------------------------------------------


def collect(
    client: Client,
    base: str,
    label: str,
    first: date,
    last: date,
) -> dict[str, dict]:
    """
    Every repository matching `base` created within the window.

    Two mechanisms, easy to confuse. PAGINATION walks the results of
    one query through the GraphQL cursor. SLICING works around the
    1000-result cap by halving the creation-date window until each
    query fits underneath it.
    """

    window = f"created:{first.isoformat()}..{last.isoformat()}"
    search = f"{base} {window} {SORT}"

    page = client.run(search, None)
    total = page["repositoryCount"]

    if total > SEARCH_CAP and first < last:

        middle = first + (last - first) / 2

        print(f"  [{label}] {window}: {total} over the cap — splitting")

        return {
            **collect(client, base, label, first, middle),
            **collect(client, base, label, middle + timedelta(days=1), last),
        }

    found: dict[str, dict] = {}

    while True:

        for node in page["nodes"]:
            if node:
                node["_source_query"] = label
                found[node["nameWithOwner"]] = node

        if not page["pageInfo"]["hasNextPage"]:
            break

        page = client.run(search, page["pageInfo"]["endCursor"])

    # The search has no declared ordering, so GitHub applies its own
    # relevance ranking, and relevance can reshuffle between one page
    # and the next. Ordering cannot cost us anything here — every page
    # is walked, and slicing keeps each query under the cap — but an
    # unstable sort can drop an item across a page boundary, and that
    # failure is silent. Comparing what the API says exists against
    # what came back is the only thing that would reveal it.
    if len(found) != total:
        print(
            f"  [{label}] {window}: WARNING — {total} reported but "
            f"{len(found)} collected, a gap of {total - len(found)}",
            file=sys.stderr,
        )
    else:
        print(f"  [{label}] {window}: {total} reported, {len(found)} collected")

    return found


# ---------------------------------------------------------------------------
# Screening layers
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    """What the automated screening decided, and on what grounds."""

    excluded: bool = False
    criterion: str = ""
    reason: str = ""
    terms: list[str] = field(default_factory=list)


def layer_one(node: dict) -> Verdict:
    """Exact fields the API returns, requiring no interpretation."""

    if node["isFork"]:
        return Verdict(True, "EC5", "fork of another repository")

    if node["isTemplate"]:
        return Verdict(True, "EC3", "flagged as a template by its owner")

    if node["isEmpty"]:
        return Verdict(True, "EC1", "empty repository")

    if not (node.get("languages") or {}).get("nodes"):
        return Verdict(True, "EC1", "no source: no language detected")

    return Verdict()


def layer_two(node: dict) -> Verdict:
    """
    Keyword exclusion for teaching material and starting points.

    The matching field is recorded because it changes how much the
    match is worth: in the NAME it is strong evidence, in a topic or
    description it is weak, and a rater has to be able to challenge
    the call by looking at what caused it.
    """

    name = node["nameWithOwner"].split("/")[-1].lower()
    description = (node.get("description") or "").lower()
    topics = [
        entry["topic"]["name"].lower()
        for entry in (node.get("repositoryTopics") or {}).get("nodes", [])
    ]

    hits = []

    for term in EXCLUSION_TERMS:

        if term in name:
            hits.append(f"name:{term}")

        if f" {term} " in f" {description} ":
            hits.append(f"description:{term}")

        if any(term in topic for topic in topics):
            hits.append(f"topic:{term}")

    if not hits:
        return Verdict()

    return Verdict(
        True,
        "EC2/EC3",
        "example, proof of concept or boilerplate term",
        sorted(set(hits)),
    )


def other_micro(node: dict) -> Verdict:
    """
    EC1 by another "micro": the text talks about microservices, or
    microfinance, and not about micro frontends.

    Not a criterion of its own — a microservice frontend simply does
    not implement micro frontends, which is what EC1 says.

    A busca exige as palavras "micro" e "frontend", não o assunto, e
    frontend de microsserviço é a colisão mais comum — foram onze dos
    108 sobreviventes do piloto.

    A exclusão é desfeita quando o texto também menciona micro
    frontend: sistema com microsserviços atrás e micro frontends na
    frente existe, e a regra cega descartaria justamente ele.
    """

    text = " ".join(
        [
            node["nameWithOwner"].split("/")[-1],
            node.get("description") or "",
            " ".join(
                entry["topic"]["name"]
                for entry in (node.get("repositoryTopics") or {}).get(
                    "nodes", []
                )
            ),
        ]
    )

    if not OTHER_MICRO.search(text) or IS_MICROFRONTEND.search(text):
        return Verdict()

    return Verdict(
        True,
        "EC1",
        "talks about microservices or microfinance, not micro frontends",
    )


def layer_three(node: dict, min_commits: int, min_lifespan: int) -> Verdict:
    """
    EC6, abandoned on creation. An addition to the protocol.

    The protocol excludes examples and proofs of concept (EC2) but says
    nothing about how to recognise one. Keyword matching catches only
    the fraction that announces itself in its own name: in a two-month
    pilot it removed 19% of the base, while 64% of what survived had a
    lifespan of a single day — created and abandoned in one sitting.

    This cut operationalises "nobody ever came back to it". Measured
    on that pilot, the lifespan condition does nearly all the work and
    the commit count is close to redundant with it, which is what you
    would expect: a classroom exercise is several commits in one
    afternoon.

    It is an addition to the protocol as originally given, so the
    thresholds belong in the write-up alongside the sensitivity
    analysis that produced them — a decreed threshold is the kind of
    choice a committee asks about and nobody can defend afterwards.

    Note the bias it carries: lifespan is the distance from creation
    to the last push, so a repository created shortly before the
    collection date is short-lived by construction, and one published
    as a single squashed snapshot of long internal work is discarded
    wrongly.
    """

    if not (min_commits or min_lifespan):
        return Verdict()

    facts = signals(node)

    if facts["commits"] < min_commits:
        return Verdict(
            True, "EC6",
            f"{facts['commits']} commits, below the {min_commits} threshold",
        )

    if facts["lifespan_days"] < min_lifespan:
        return Verdict(
            True, "EC6",
            f"lifespan of {facts['lifespan_days']} days, "
            f"below the {min_lifespan} threshold",
        )

    return Verdict()


def structure(paths: list[str] | None) -> dict:
    """
    How much code the repository holds, and how many applications.

    Two counts, both from the file tree. Source files measure whether
    there is a system here at all: across a two-month pilot the median
    survivor held 25 of them, and fewer than one in ten reached 84 —
    numbers that describe exercises, not systems.

    The count of package.json files is the structural shape of a micro
    frontend repository: several applications side by side. It is not
    framework detection, which fails badly here — only 8% of that
    pilot declared a known framework anywhere, while 38% had no
    package.json at the root at all, because in this architecture each
    micro frontend carries its own inside a subdirectory. Counting
    them sees a hand-rolled composition exactly as well as an
    off-the-shelf one.

    Neither count decides anything on its own. A repository split one
    micro frontend per repository shows a single package.json and is
    still a micro frontend; that is a limit of the measure, not of the
    system.
    """

    if paths is None:
        return {"source_files": "", "package_json_count": ""}

    own = [path for path in paths if not NOT_SOURCE.search(path)]

    return {
        "source_files": sum(1 for path in own if SOURCE_FILE.search(path)),
        "package_json_count": sum(
            1 for path in own if path.endswith("package.json")
        ),
    }


def layer_four(facts: dict, min_source: int) -> Verdict:
    """
    EC7, too small to be a unit. Off unless requested.

    The threshold is the floor of a UNIT, not of a system. A system
    split across repositories puts one micro frontend per repository,
    and a micro frontend is small by design — the seven units of the
    healthcare system hold between 13 and 28 source files each. A
    threshold set for a whole system would discard every one of them.

    Counting `package.json` files, which an earlier version did, is
    the same mistake in sharper form: a unit has exactly one.
    """

    if not min_source:
        return Verdict()

    if facts["source_files"] == "":
        return Verdict()

    if facts["source_files"] < min_source:
        return Verdict(
            True, "EC7",
            f"{facts['source_files']} source files, "
            f"below the {min_source} threshold",
        )

    return Verdict()


def signals(node: dict) -> dict:
    """
    Evidence for the human judgement. Nothing here excludes anything.

    These are the indications that a repository is a real system
    rather than disposable material, but none of them decides on its
    own, and the thresholds are calibrated against the pilot rather
    than decreed in advance.
    """

    branch = node.get("defaultBranchRef") or {}
    head = (branch.get("target") or {}) if branch else {}

    created = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))

    pushed = node.get("pushedAt")
    pushed = (
        datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        if pushed
        else created
    )

    return {
        "commits": (head.get("history") or {}).get("totalCount", 0),
        "lifespan_days": (pushed - created).days,
        "created_at": created.date().isoformat(),
        "last_push": pushed.date().isoformat(),
        "stars": node["stargazerCount"],
        "forks": node["forkCount"],
        "watchers": (node.get("watchers") or {}).get("totalCount", 0),
        "issues": (node.get("issues") or {}).get("totalCount", 0),
        "pull_requests": (node.get("pullRequests") or {}).get("totalCount", 0),
        "releases": (node.get("releases") or {}).get("totalCount", 0),
        "size_kb": node.get("diskUsage") or 0,
        "archived": node["isArchived"],
        "license": (node.get("licenseInfo") or {}).get("key", ""),
        "language": (node.get("primaryLanguage") or {}).get("name", ""),
        "languages": "; ".join(
            entry["name"]
            for entry in (node.get("languages") or {}).get("nodes", [])
        ),
        "topics": "; ".join(
            entry["topic"]["name"]
            for entry in (node.get("repositoryTopics") or {}).get("nodes", [])
        ),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

COLUMNS = [
    "repository", "url", "description", "homepage", "source_query",
    "auto_excluded", "criterion", "reason", "matched_terms",
    "commits", "lifespan_days", "created_at", "last_push",
    "stars", "forks", "watchers", "issues", "pull_requests",
    "releases", "size_kb", "archived", "license",
    "language", "languages", "topics",
    "source_files", "package_json_count",
    # left blank for the manual assessment
    "i2_implements_mfe", "e2_is_real", "e4_is_framework",
    "technology", "mfe_count", "included", "rater", "notes",
]


def row(node: dict, verdict: Verdict) -> dict:

    return {
        "repository": node["nameWithOwner"],
        "url": node["url"],
        "description": (node.get("description") or "").replace("\n", " "),
        "homepage": node.get("homepageUrl") or "",
        "source_query": node.get("_source_query", ""),
        "auto_excluded": "yes" if verdict.excluded else "no",
        "criterion": verdict.criterion,
        "reason": verdict.reason,
        "matched_terms": "; ".join(verdict.terms),
        **signals(node),
        "source_files": "",
        "package_json_count": "",
        "i2_implements_mfe": "",
        "e2_is_real": "",
        "e4_is_framework": "",
        "technology": "",
        "mfe_count": "",
        "included": "",
        "rater": "",
        "notes": "",
    }


def write(path: Path, rows: list[dict], header: list[str]) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as handle:

        for note in header:
            handle.write(f"# {note}\n")

        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Mine and screen micro frontend repositories from GitHub, "
            "following the selection protocol documented in this file."
        )
    )
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument(
        "--since", default="2008-01-01",
        help=(
            "start of the creation window. Default: 2008-01-01, when "
            "GitHub itself began — the window is a pagination device, "
            "not a criterion, so it must not exclude anything."
        ),
    )
    parser.add_argument(
        "--until", default=date.today().isoformat(),
        help="end of the creation window. Default: today",
    )
    parser.add_argument(
        "--pause", type=float, default=1.0,
        help="seconds between requests. Default: 1.0",
    )
    parser.add_argument(
        "--min-commits", type=int, default=0,
        help=(
            "EC6: discard below this many commits. The protocol uses "
            "20."
        ),
    )
    parser.add_argument(
        "--min-source-files", type=int, default=0,
        help=(
            "EC7: discard below this many source files, the floor of "
            "a unit and not of a system. The protocol uses 10. "
            "Requires the probe."
        ),
    )
    parser.add_argument(
        "--siblings", action="store_true",
        help=(
            "list every repository of each surviving owner, so a "
            "system split across repositories can be reassembled"
        ),
    )
    parser.add_argument(
        "--no-probe", action="store_true",
        help=(
            "skip the structure probe, which costs one extra request "
            "per surviving repository"
        ),
    )
    parser.add_argument(
        "--min-lifespan-days", type=int, default=0,
        help=(
            "EC6: discard below this many days between creation and "
            "last push. The protocol uses 7."
        ),
    )

    options = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not token:
        print(
            "Set GITHUB_TOKEN. The GitHub GraphQL API rejects "
            "unauthenticated requests.",
            file=sys.stderr,
        )
        return 1

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    first = date.fromisoformat(options.since)
    last = date.fromisoformat(options.until)

    print(f"Window: {options.since} .. {options.until}\n")

    client = Client(token, options.pause)

    # Keyed on nameWithOwner: a repository is collected once.
    found = collect(client, SEARCH_STRING, "search-string", first, last)

    # ---- layers 1 and 2

    rows, kept = [], []
    counts = {
        "total": len(found),
        "layer_1": 0, "layer_2": 0, "layer_3": 0, "layer_4": 0,
    }

    for node in found.values():

        verdict = layer_one(node)

        if verdict.excluded:
            counts["layer_1"] += 1
        else:
            verdict = layer_two(node)
            if verdict.excluded:
                counts["layer_2"] += 1
            elif other_micro(node).excluded:
                verdict = other_micro(node)
                counts["layer_2"] += 1
            else:
                verdict = layer_three(
                    node, options.min_commits, options.min_lifespan_days
                )
                if verdict.excluded:
                    counts["layer_3"] += 1

        record = row(node, verdict)
        rows.append(record)

        if not verdict.excluded:
            kept.append(record)

    # ---- layer 4: structure probe, one REST call per survivor
    #
    # Probed after the cheap layers, never before: there is no reason
    # to spend a request on a repository already excluded. The counts
    # are recorded whether or not a threshold is set, because they are
    # the evidence a rater needs even when nothing is being cut.

    if not options.no_probe and kept:

        print(f"\nProbing structure of {len(kept)} repositories")

        surviving = []

        for position, record in enumerate(kept, start=1):

            facts = structure(client.tree(record["repository"]))
            record.update(facts)

            verdict = layer_four(
                facts, options.min_source_files
            )

            if verdict.excluded:
                counts["layer_4"] += 1
                record["auto_excluded"] = "yes"
                record["criterion"] = verdict.criterion
                record["reason"] = verdict.reason
            else:
                surviving.append(record)

            if position % 50 == 0:
                print(f"  {position}/{len(kept)}")

            time.sleep(options.pause)

        kept = surviving

    header = [
        f"collected: {timestamp}",
        f"search string: {SEARCH_STRING}",
        f"creation window: {options.since} .. {options.until}",
        f"ordering: {SORT}",
        "vitality cut: "
        + (
            f">= {options.min_commits} commits, "
            f">= {options.min_lifespan_days} days lifespan"
            if (options.min_commits or options.min_lifespan_days)
            else "none"
        ),
        "size cut: "
        + (
            f">= {options.min_source_files} source files"
            if options.min_source_files
            else "none"
        ),
        f"structure probe: {'skipped' if options.no_probe else 'yes'}",
        f"API requests: {client.requests}",
    ]

    # ---- owners, for systems split across repositories

    if options.siblings and kept:

        owners = sorted({row["repository"].split("/")[0] for row in kept})

        print(f"\nListing repositories of {len(owners)} owners")

        siblings = []

        for position, login in enumerate(owners, start=1):

            candidates = {
                row["repository"]
                for row in kept
                if row["repository"].startswith(f"{login}/")
            }

            for node in client.owned_by(login):

                if node.get("isEmpty"):
                    continue

                siblings.append(
                    {
                        "owner": login,
                        "repository": node["nameWithOwner"],
                        "matched_search": (
                            "yes"
                            if node["nameWithOwner"] in candidates
                            else "no"
                        ),
                        "url": node["url"],
                        "description": (
                            node.get("description") or ""
                        ).replace("\n", " "),
                        "last_push": (node.get("pushedAt") or "")[:10],
                        "language": (
                            node.get("primaryLanguage") or {}
                        ).get("name", ""),
                        "topics": "; ".join(
                            entry["topic"]["name"]
                            for entry in (
                                node.get("repositoryTopics") or {}
                            ).get("nodes", [])
                        ),
                        "same_system": "",
                        "rater": "",
                    }
                )

            if position % 25 == 0:
                print(f"  {position}/{len(owners)}")

            time.sleep(options.pause)

        columns = [
            "owner", "repository", "matched_search", "url",
            "description", "last_push", "language", "topics",
            "same_system", "rater",
        ]

        siblings.sort(key=lambda row: (row["owner"], row["repository"]))

        path = options.output / "siblings.csv"

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as handle:

            for note in header:
                handle.write(f"# {note}\n")

            handle.write(
                "# one row per repository of every surviving owner; "
                "fill same_system to group them\n"
            )

            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(siblings)

        counts["siblings"] = len(siblings)
        counts["owners"] = len(owners)


    # Sorted by name, not left in the order the API returned them.
    # GitHub sorts by relevance, which is not stable between runs: the
    # same collection can come back in a different order, and then two
    # runs cannot be diffed against each other.
    rows.sort(key=lambda record: record["repository"].lower())
    kept.sort(key=lambda record: record["repository"].lower())

    write(options.output / "raw.csv", rows, header)
    write(
        options.output / "screened.csv", kept,
        header + ["survivors of screening layers 1 and 2"],
    )

    summary = [
        "Repository mining and automated screening",
        "=" * 58,
        f"collected at              {timestamp}",
        f"search string             {SEARCH_STRING}",
        f"creation window           {options.since} .. {options.until}",
        f"ordering                  {SORT}",
        f"API requests              {client.requests}",
        "",
        f"distinct repositories     {counts['total']}",
        f"excluded by layer 1       {counts['layer_1']}"
        "        (EC5 fork, EC3 template, EC1 empty or no code)",
        f"excluded by layer 2       {counts['layer_2']}"
        "        (EC2/EC3 example, POC or boilerplate terms)",
        f"excluded by layer 3       {counts['layer_3']}"
        "        (EC6 abandoned on creation)",
        f"excluded by layer 4       {counts['layer_4']}"
        "        (EC7 no mass of code)",
        f"left for manual review    {len(kept)}",
    ] + ([
        "",
        f"owners listed             {counts.get('owners', 0)}",
        f"sibling repositories      {counts.get('siblings', 0)}"
        "        (in siblings.csv, to be grouped by hand)",
    ] if options.siblings else []) + [
        "",
        "Criteria IC2 (a system with two or more micro frontends) and",
        "EC4 (framework or library) are not decided here — they are",
        "judgement calls, and",
        "the corresponding columns in screened.csv are left blank to be",
        "filled in by the raters.",
    ]

    (options.output / "summary.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )

    print("\n" + "\n".join(summary))

    return 0


if __name__ == "__main__":
    sys.exit(main())
