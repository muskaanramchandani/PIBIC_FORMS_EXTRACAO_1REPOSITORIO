"""
Roda o LLM as a judge pelo OpenRouter sobre os prompts de `sistemas/`.

Uso:
  export OPENROUTER_API_KEY=...
  python3 run_judge.py [--model <id>] [--only <sistema>] [--execucao <n>] [--dry-run]
  python3 run_judge.py --batch submit   # manda pela fila do OpenRouter (metade do preço)
  python3 run_judge.py --batch poll     # busca o que a fila já respondeu

Para cada linha do `sistemas/manifest.csv`, manda o prompt, confere a
resposta e grava o registro em `runs/<modelo>/`. Chamada já registrada
com sucesso é pulada: dá para interromper e continuar. No fim, monta
`respostas/<modelo>/execucao-<n>/avaliacao-<sistema>.csv` na ordem
original. O modelo padrão é o da avaliação, `openai/gpt-5`.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
PROMPTS = HERE / "sistemas"
RUNS_ROOT = HERE / "runs"
ANSWERS_ROOT = HERE / "respostas"
CSVS = HERE / "../../profissionais"

API = "https://openrouter.ai/api/v1"
URL = f"{API}/chat/completions"

# Só IPv4: em rede com IPv6 quebrado, cada chamada esperava o IPv6 falhar.
_resolve = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *rest: _resolve(host, port, socket.AF_INET, *rest)

MODEL = "openai/gpt-5"


def parameters(model: str) -> dict:
    """Os da avaliação; o provedor só é travado para o GPT-5."""

    chosen = {
        "model": model,
        "reasoning": {"effort": "high"},
        "max_tokens": 16000,
        "usage": {"include": True},
    }

    if model == MODEL:
        chosen["provider"] = {"order": ["openai"], "allow_fallbacks": False}

    return chosen


def slug(model: str) -> str:
    return model.replace("/", "-").replace(":", "-")

RETRIES = 2
FIXED = 4  # #, anti-padrão, micro frontends, endpoint
JUDGMENTS = ("Sim", "Não", "Não sei")


def split(prompt: str) -> tuple[str, str]:
    system, user = prompt.split("\n# USER\n", 1)
    return system.removeprefix("# SYSTEM\n").strip(), user.strip()


def http(method: str, url: str, body: dict | None = None) -> dict:

    request = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


def call(system: str, user: str, chosen: dict) -> dict:

    return http("POST", URL, dict(chosen, messages=[
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]))


def table(text: str) -> list[list[str]]:
    """O CSV da resposta, sem cercas de código nem texto em volta."""

    lines = [line for line in text.strip().splitlines() if not line.startswith("```")]
    return [row for row in csv.reader(io.StringIO("\n".join(lines))) if row]


def realign(row: list[str]) -> list[str]:
    """Tira a coluna vazia que alguns modelos põem antes do julgamento.

    Só quando a coluna do julgamento está vazia e a seguinte traz um
    julgamento válido; vale igual para todos os modelos."""

    if len(row) > FIXED + 1 and row[FIXED] == "" and row[FIXED + 1] in JUDGMENTS:
        return row[:FIXED] + row[FIXED + 1:]

    return row


def answer_rows(text: str) -> tuple[list[list[str]], int]:
    """As linhas da resposta, realinhadas, e quantas precisaram disso."""

    rows = table(text)
    fixed = [realign(row) for row in rows]

    return fixed, sum(a != b for a, b in zip(rows, fixed))


def check(sent: list[list[str]], got: list[list[str]]) -> str | None:
    """`None` se a resposta tem as mesmas linhas, com as colunas fixas iguais."""

    expected = {row[0]: row for row in sent[1:]}
    answered = {row[0]: row for row in got if row and row[0] in expected}

    if set(answered) != set(expected):
        return f"linhas esperadas {sorted(expected)}, recebidas {sorted(answered)}"

    for number, row in answered.items():
        if row[:FIXED] != expected[number][:FIXED]:
            return f"linha {number} alterada: {row[:FIXED]}"
        if len(row) < FIXED + 1 or row[FIXED] not in JUDGMENTS:
            return f"linha {number} sem julgamento válido: {row[FIXED:]}"

    return None


def sent_rows(user: str) -> list[list[str]]:
    return table(user.split("Planilha a preencher:", 1)[1])


def run_one(entry: dict, template_hash: str, dry: bool, model: str) -> None:

    chosen = parameters(model)
    record = RUNS_ROOT / slug(model) / entry["arquivo"].replace(".md", ".json")

    if record.exists() and json.loads(record.read_text()).get("ok"):
        return

    system, user = split((PROMPTS / entry["arquivo"]).read_text(encoding="utf-8"))
    sent = sent_rows(user)

    if dry:
        print(f"[dry] {entry['arquivo']}: {len(sent) - 1} linhas, {len(system) + len(user)} caracteres")
        return

    attempts = []

    for attempt in range(RETRIES + 1):

        started = datetime.now(timezone.utc).isoformat()

        try:
            response = call(system, user, chosen)
            if "choices" not in response:
                raise RuntimeError(json.dumps(response.get("error", response))[:500])
        except Exception as error:  # rede, limite, timeout: registra e tenta de novo
            attempts.append({"started": started, "error": repr(error)})
            time.sleep(10 * (attempt + 1))
            continue

        attempts.append(attempt_of(response, sent, started))

        if attempts[-1]["problem"] is None:
            break

    save(record, entry, template_hash, chosen, system, user, attempts)


def attempt_of(response: dict, sent: list[list[str]], started: str) -> dict:
    """Uma tentativa, com a resposta conferida contra as linhas enviadas."""

    message = response["choices"][0]["message"]
    rows, realigned = answer_rows(message.get("content") or "")

    return {
        "started": started,
        "id": response.get("id"),
        "model": response.get("model"),
        "provider": response.get("provider"),
        "usage": response.get("usage"),
        "content": message.get("content"),
        "reasoning": message.get("reasoning"),
        "realigned": realigned,
        "problem": check(sent, rows),
    }


def save(record: Path, entry: dict, template_hash: str, chosen: dict, system: str, user: str, attempts: list) -> None:

    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({
        **entry,
        "ok": attempts[-1].get("problem", "erro") is None,
        "template_sha256": template_hash,
        "parameters": chosen,
        "system": system,
        "user": user,
        "attempts": attempts,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    status = "ok" if attempts[-1].get("problem", "erro") is None else "FALHOU"
    print(f"{status} {entry['arquivo']}")


def previous(record: Path) -> list:
    """As tentativas já registradas: o reenvio pela fila acrescenta, não apaga."""

    return json.loads(record.read_text()).get("attempts", []) if record.exists() else []


def submit(entries: list[dict], model: str) -> None:
    """Um lote da fila por execução, só com o que ainda não tem resposta válida."""

    chosen = parameters(model)
    root = RUNS_ROOT / slug(model)
    pending = pending_ids(root)

    by_execution: dict[str, list] = {}

    for entry in entries:
        record = root / entry["arquivo"].replace(".md", ".json")
        if record.exists() and json.loads(record.read_text()).get("ok"):
            continue
        if entry["arquivo"] in pending:
            continue
        by_execution.setdefault(entry["execucao"], []).append(entry)

    for execution, chosen_entries in sorted(by_execution.items()):

        requests = []

        for entry in chosen_entries:
            system, user = split((PROMPTS / entry["arquivo"]).read_text(encoding="utf-8"))
            body = {key: value for key, value in chosen.items() if key not in ("model", "provider")}
            body["messages"] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            requests.append({"custom_id": entry["arquivo"], "body": body})

        batch = {"endpoint": "/v1/chat/completions", "model": model, "requests": requests}

        if "provider" in chosen:
            batch["provider"] = {"only": chosen["provider"]["order"]}

        response = http("POST", f"{API}/batches", batch)

        folder = root / "batches"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{response['id']}.json").write_text(json.dumps({
            "id": response["id"],
            "execution": execution,
            "submitted": datetime.now(timezone.utc).isoformat(),
            "entries": [entry["arquivo"] for entry in chosen_entries],
            "status": response.get("status"),
        }, indent=1))

        print(f"lote {response['id']}: execução {execution}, {len(requests)} pedidos, {response.get('status')}")


def pending_ids(root: Path) -> set[str]:
    """Os pedidos que estão numa fila ainda não terminada."""

    found = set()

    for path in (root / "batches").glob("*.json") if (root / "batches").exists() else []:
        data = json.loads(path.read_text())
        if data.get("status") not in ("completed", "failed", "expired", "cancelled"):
            found.update(data["entries"])

    return found


def poll(entries: list[dict], template_hash: str, model: str) -> None:
    """Busca os lotes da fila; o que terminou vira registro, como na chamada direta."""

    chosen = parameters(model)
    root = RUNS_ROOT / slug(model)
    by_file = {entry["arquivo"]: entry for entry in entries}

    for path in sorted((root / "batches").glob("*.json")) if (root / "batches").exists() else []:

        saved = json.loads(path.read_text())

        if saved.get("status") in ("completed", "failed", "expired", "cancelled"):
            continue

        batch = http("GET", f"{API}/batches/{saved['id']}")
        saved["status"] = batch.get("status")
        print(f"lote {saved['id']}: {saved['status']}")

        if saved["status"] == "completed":

            for result in batch.get("results") or []:

                entry = by_file[result["custom_id"]]
                record = root / entry["arquivo"].replace(".md", ".json")
                system, user = split((PROMPTS / entry["arquivo"]).read_text(encoding="utf-8"))
                started = saved["submitted"]

                if result.get("error"):
                    attempt = {"started": started, "batch": saved["id"], "error": json.dumps(result["error"])[:500]}
                else:
                    attempt = attempt_of(result["response"]["body"], sent_rows(user), started)
                    attempt["batch"] = saved["id"]

                save(record, entry, template_hash, chosen, system, user, previous(record) + [attempt])

        path.write_text(json.dumps(saved, indent=1))


def assemble(model: str) -> None:
    """Junta os lotes de cada execução no CSV do sistema, na ordem original."""

    runs = RUNS_ROOT / slug(model)

    for original in sorted(CSVS.glob("avaliacao-*.csv")):

        name = original.stem.removeprefix("avaliacao-")

        with original.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))

        for execution in (1, 2, 3):

            answers = {}

            for record in sorted((runs / name).glob(f"execucao-{execution}-lote-*.json")):
                data = json.loads(record.read_text())
                if data.get("ok"):
                    for row in answer_rows(data["attempts"][-1]["content"])[0]:
                        answers[row[0]] = row

            if not answers:
                continue

            filled = [rows[0]] + [answers.get(row[0], row) for row in rows[1:]]

            target = ANSWERS_ROOT / slug(model) / f"execucao-{execution}" / original.name
            target.parent.mkdir(parents=True, exist_ok=True)

            with target.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.writer(handle).writerows(filled)


def recheck(entries: list[dict], model: str) -> None:
    """Confere de novo, com as regras atuais, a última resposta das chamadas que falharam."""

    root = RUNS_ROOT / slug(model)

    for entry in entries:

        record = root / entry["arquivo"].replace(".md", ".json")
        if not record.exists():
            continue

        data = json.loads(record.read_text())
        last = data["attempts"][-1]
        if data.get("ok") or not last.get("content"):
            continue

        rows, realigned = answer_rows(last["content"])
        last["realigned"] = realigned
        last["problem"] = check(sent_rows(data["user"]), rows)
        last["rechecked"] = datetime.now(timezone.utc).isoformat()
        data["ok"] = last["problem"] is None
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

        print(f"{'ok' if data['ok'] else 'FALHOU'} {entry['arquivo']}: {realigned} linhas realinhadas")


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--only")
    parser.add_argument("--execucao", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", choices=["submit", "poll"])
    parser.add_argument("--reconferir", action="store_true", help="confere de novo as respostas que falharam, sem chamar o modelo")
    arguments = parser.parse_args()

    if not (arguments.dry_run or arguments.reconferir) and "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("defina OPENROUTER_API_KEY")

    template_hash = hashlib.sha256((HERE / "template.md").read_bytes()).hexdigest()

    with (PROMPTS / "manifest.csv").open(encoding="utf-8") as handle:
        entries = list(csv.DictReader(handle))

    entries = [
        entry for entry in entries
        if (not arguments.only or entry["sistema"] == arguments.only)
        and (not arguments.execucao or int(entry["execucao"]) == arguments.execucao)
    ]

    if arguments.reconferir:
        recheck(entries, arguments.model)
        assemble(arguments.model)
        return

    if arguments.batch == "submit":
        submit(entries, arguments.model)
        return

    if arguments.batch == "poll":
        poll(entries, template_hash, arguments.model)
        assemble(arguments.model)
        return

    for entry in entries:
        run_one(entry, template_hash, arguments.dry_run, arguments.model)

    if not arguments.dry_run:
        assemble(arguments.model)


if __name__ == "__main__":
    main()
