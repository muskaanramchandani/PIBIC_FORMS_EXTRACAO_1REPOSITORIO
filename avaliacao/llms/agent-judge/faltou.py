"""
Parte 2 do agent as a judge: o que a reconstrução deixou de extrair.

Uso:
  export OPENROUTER_API_KEY=...
  python3 faltou.py --sortear                      # escreve faltou/amostra.csv
  python3 faltou.py --model <id> [--only <sistema>] [--execucao <n>] [--paralelo <n>]
  python3 faltou.py --sortear-mais udistrital 10    # escreve faltou/amostra-udistrital.csv
  python3 faltou.py --model <id> --amostra faltou/amostra-udistrital.csv

Um micro frontend sorteado por sistema (semente `faltou-<sistema>`), da
reconstrução corrigida em `../reconstrucao-corrigida/`. O agente recebe o
que o DAMFE extraiu dele e procura no código o que ficou de fora. Uma
sessão por sistema e execução, em
`runs-faltou/<modelo>/<sistema>/execucao-<n>.json`; sessão já registrada
com sucesso é pulada.
"""

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from run_agent import CODE, EXECUTIONS, HERE, Repository, Unfinished, parameters, session, slug, system_prompt

ARTIFACTS = HERE / "../reconstrucao-corrigida"
SAMPLE = HERE / "faltou" / "amostra.csv"
RUNS = HERE / "runs-faltou"
EXCLUDED = {"nabstore", "halloween"}
RETRIES = 8
TRANSIENT = ("overloaded", "429", "503", "502", "rate limit", "Rate limit")
TASK = "Você vai receber itens extraídos pelo DAMFE. Para cada um, confira no código se ele é verdadeiro."
TASK_MISSING = (
    "Nesta sessão, você vai receber tudo o que o DAMFE extraiu de um micro frontend. Procure no código "
    "o que ele deveria ter extraído e não extraiu, e responda no formato da busca do que faltou."
)
KINDS = {"micro frontend", "tela", "fragmento", "composição", "navegação", "comunicação", "chamada de API", "acesso a estado"}


def load(system: str, name: str) -> list:
    return json.loads((ARTIFACTS / system / f"{name}.json").read_text(encoding="utf-8"))


def where(at: dict | None) -> str:
    return f"{at['file']}:{at['line']}" if at else "?"


def places(locations: list, limit: int = 4) -> str:
    """Até `limit` locais e quantos ficaram de fora: no udistrital, um canal de storage tem centenas."""

    shown = ", ".join(where(at) for at in locations[:limit])
    return shown + (f" (+{len(locations) - limit} locais)" if len(locations) > limit else "")


def draw() -> None:
    """Um micro frontend por sistema, com a semente registrada."""

    rows = []

    for folder in sorted(ARTIFACTS.iterdir()):

        if not folder.is_dir() or folder.name in EXCLUDED:
            continue

        units = sorted(load(folder.name, "microfrontends"), key=lambda unit: unit["id"])
        seed = f"faltou-{folder.name}"
        chosen = random.Random(seed).choice(units)
        rows.append({"sistema": folder.name, "mfe": chosen["id"], "diretorio": chosen.get("directory", ""), "semente": seed})

    SAMPLE.parent.mkdir(parents=True, exist_ok=True)

    with SAMPLE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sistema", "mfe", "diretorio", "semente"])
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(row["sistema"], row["mfe"], row["diretorio"])


def draw_more(system: str, count: int) -> None:
    """Mais micro frontends de um sistema, sem repetir o já sorteado, com semente própria."""

    with SAMPLE.open(encoding="utf-8") as handle:
        taken = {row["mfe"] for row in csv.DictReader(handle) if row["sistema"] == system}

    units = sorted((unit for unit in load(system, "microfrontends") if unit["id"] not in taken), key=lambda unit: unit["id"])
    seed = f"faltou-{system}-mais"
    chosen = random.Random(seed).sample(units, count)
    rows = [{"sistema": system, "mfe": unit["id"], "diretorio": unit.get("directory", ""), "semente": seed} for unit in chosen]

    with (SAMPLE.parent / f"amostra-{system}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sistema", "mfe", "diretorio", "semente"])
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(row["sistema"], row["mfe"], row["diretorio"])


def extracted(system: str, mfe: str, directory: str = "") -> str:
    """O que o DAMFE extraiu do micro frontend, um item por linha, com arquivo:linha."""

    # Pelo diretório quando há: no udistrital, os 7 shells saem com o mesmo id.
    unit = next(unit for unit in load(system, "microfrontends")
                if unit["id"] == mfe and (not directory or unit.get("directory") == directory))
    lines = [f"- papel: {unit.get('role')}; rotas em que é montado: {', '.join(unit.get('routes') or []) or '(nenhuma)'}"]

    lines += ["", "Telas:"] + [
        f"- {screen['component']} na rota {screen.get('route') or '(sem rota)'} | {screen.get('file')}:{screen.get('line')}"
        for screen in unit.get("screens") or []
    ] or ["- (nenhuma)"]

    lines += ["", "Fragmentos expostos:"] + [
        f"- {fragment['name']} | {fragment.get('file')}:{fragment.get('line')}" for fragment in unit.get("fragments") or []
    ]

    lines += ["", "Composições (quem monta o fragmento de quem):"] + [
        f"- {item['consumer']} monta {item['fragment']} de {item['provider']} | {where(item.get('imported_at'))}"
        for item in load(system, "compositions") if mfe in (item["consumer"], item["provider"])
    ]

    lines += ["", "Navegações:"] + [
        f"- {item['source']} → {item['target']} pela URL {item.get('resolved_url')} | {where(item.get('at'))}"
        for item in load(system, "navigations") if mfe in (item["source"], item["target"])
    ]

    lines += ["", "Comunicações:"] + [
        f"- {item['source']} → {item['target']} pelo canal {item.get('channel')} ({item.get('mechanism')}) | "
        + places((item.get("produced_at") or []) + (item.get("consumed_at") or []))
        for item in load(system, "communications") if mfe in (item["source"], item["target"])
    ]

    lines += ["", "Chamadas de API:"] + [
        f"- {item['method']} {item['path']} ({item.get('client')}) | {where(item.get('at'))}"
        for item in load(system, "api_calls") if item["microfrontend"] == mfe
    ]

    lines += ["", "Acessos a estado:"] + [
        f"- {item['access']} {item['library']} {item['path']} | {where(item.get('at'))}"
        for item in load(system, "state_accesses") if item["microfrontend"] == mfe
    ]

    # Seção sem item fica com "(nenhum)", para o agente não supor que faltou o dado.
    out = []
    for index, line in enumerate(lines):
        out.append(line)
        if line.endswith(":") and (index + 1 == len(lines) or not lines[index + 1].startswith("- ")):
            out.append("- (nenhum)")

    return "\n".join(out)


def user_prompt(row: dict) -> str:
    return (
        f"Sistema: {row['sistema']}\n\n"
        f"Micro frontend: {row['mfe']} (diretório {row['diretorio']})\n\n"
        f"O DAMFE extraiu dele:\n{extracted(row['sistema'], row['mfe'], row.get('diretorio', ''))}\n\n"
        "Procure no código deste micro frontend o que o DAMFE deveria ter extraído e não extraiu: "
        "telas, fragmentos, composições, navegações, comunicações, chamadas de API e acessos a estado. "
        "Responda uma linha JSON por item faltante, no formato da busca do que faltou, com `tipo` sendo um de: "
        + ", ".join(sorted(KINDS))
        + '. Termine sempre com a linha {"fim": true}, mesmo que não falte nada.'
    )


def objects(text: str):
    """Os objetos JSON do texto, um por linha ou colados na mesma linha."""

    decoder = json.JSONDecoder()
    index = 0
    text = text or ""

    while (index := text.find("{", index)) != -1:
        try:
            item, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(item, dict):
            yield item
        index = end


def answers(text: str) -> tuple[list[dict], bool]:
    """As ocorrências e se a resposta chegou até a linha de fim."""

    found, finished = [], False

    for item in objects(text):
        if item.get("fim"):
            finished = True
        elif item.get("faltante") or "faltante" in item:
            found.append(item)

    return found, finished


def plain(text: str) -> str:
    """Sem acento nem caixa: "comunicacao" e "Comunicação" são o mesmo tipo."""

    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def kind(item: dict) -> str | None:
    """O tipo do item, na grafia da tabela, aceitando o singular e o plural."""

    def singular(text: str) -> str:
        words = plain(text).split()
        return " ".join(word[:-4] + "cao" if word.endswith("coes") else word.removesuffix("s") for word in words)

    given = singular(item.get("tipo"))
    return next((name for name in KINDS if singular(name) == given), None)


def check(found: list[dict], finished: bool) -> str | None:
    for item in found:
        item["tipo"] = kind(item) or item.get("tipo")
    if not finished:
        return "sem a linha de fim"
    bad = [item for item in found if item.get("tipo") not in KINDS or not item.get("evidencia")]
    return f"itens sem tipo válido ou sem evidência: {len(bad)}" if bad else None


def recheck(record) -> bool:
    """Confere de novo, com as regras atuais, uma resposta já gravada que falhou."""

    data = json.loads(record.read_text())
    if not data.get("content"):
        return False
    found, finished = answers(data["content"])
    data["missing"], data["problem"] = found, check(found, finished)
    data["ok"] = data["problem"] is None
    if data["ok"]:
        data["rechecked"] = datetime.now(timezone.utc).isoformat()
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data["ok"]


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--sortear", action="store_true")
    parser.add_argument("--sortear-mais", nargs=2, metavar=("SISTEMA", "N"), help="mais MFEs de um sistema")
    parser.add_argument("--amostra", help="outra amostra, como faltou/amostra-udistrital.csv")
    parser.add_argument("--model")
    parser.add_argument("--only")
    parser.add_argument("--execucao", type=int)
    parser.add_argument("--provider")
    parser.add_argument("--paralelo", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    if arguments.sortear:
        draw()
        return

    if arguments.sortear_mais:
        draw_more(arguments.sortear_mais[0], int(arguments.sortear_mais[1]))
        return

    if not arguments.model:
        sys.exit("informe --model")

    chosen_sample = HERE / arguments.amostra if arguments.amostra else SAMPLE
    with chosen_sample.open(encoding="utf-8") as handle:
        sample = list(csv.DictReader(handle))

    if arguments.dry_run:
        for row in sample:
            if not arguments.only or row["sistema"] == arguments.only:
                print(f"--- {row['sistema']} ({len(user_prompt(row))} caracteres)\n{user_prompt(row)[:1500]}\n")
        return

    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("defina OPENROUTER_API_KEY")

    # O System é o da parte 1, com a tarefa trocada: sem isso, modelos
    # menores respondem conferindo itens, no formato da parte 1.
    system = system_prompt().replace(TASK, TASK_MISSING)
    assert TASK_MISSING in system
    template_hash = hashlib.sha256((HERE / "template.md").read_bytes()).hexdigest()
    chosen = parameters(arguments.model, arguments.provider)
    folder = RUNS / slug(arguments.model)

    jobs = []
    for row in sample:
        if arguments.only and row["sistema"] != arguments.only:
            continue
        for execution in range(1, EXECUTIONS + 1):
            if arguments.execucao and execution != arguments.execucao:
                continue
            # Na amostra extra, um MFE por pasta, abaixo da do sistema.
            base = folder / row["sistema"] / (slug(row["diretorio"]) if arguments.amostra else "")
            record = base / f"execucao-{execution}.json"
            if not (record.exists() and (json.loads(record.read_text()).get("ok") or recheck(record))):
                jobs.append((row, execution, record))

    def run(job) -> None:

        row, execution, record = job
        started = datetime.now(timezone.utc).isoformat()

        # Os gratuitos devolvem "sobrecarregado" ou limite de taxa no meio do
        # streaming, que o `http` não tenta de novo: a sessão recomeça.
        for attempt in range(RETRIES + 1):
            try:
                result = session(Repository(CODE / row["sistema"]), system, user_prompt(row), chosen)
                found, finished = answers(result["content"])
                problem = check(found, finished)
            except Unfinished as error:
                result, found, problem = error.partial, [], str(error)
            if problem is None or not any(code in problem for code in TRANSIENT) or attempt == RETRIES:
                break
            time.sleep(min(60 * (attempt + 1), 300))

        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({
            "ok": problem is None, "problem": problem, "started": started,
            "system": row["sistema"], "mfe": row["mfe"], "execution": execution,
            "missing": found,
            "parameters": {key: value for key, value in chosen.items() if key != "tools"},
            "template_sha256": template_hash, **result,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        print(f"{'ok' if problem is None else 'FALHOU'} {row['sistema']} exec {execution}: "
              f"{len(found)} faltantes, {result.get('tool_calls', 0)} ferramentas"
              + (f" — {problem}" if problem else ""), flush=True)

    with ThreadPoolExecutor(max_workers=arguments.paralelo) as pool:
        list(pool.map(run, jobs))


if __name__ == "__main__":
    main()
