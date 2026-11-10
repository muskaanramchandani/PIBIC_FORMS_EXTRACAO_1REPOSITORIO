"""
Roda o agente extrator pelo OpenRouter: o modelo responde às 15 perguntas do
`meu_formulario.json` lendo o código do sistema com três ferramentas só de leitura.

Uso:
  export OPENROUTER_API_KEY=...
  python3 run_agent.py --model <id> [--repos <pasta>] [--only <sistema>] [--execucao <n>] [--provider <p>] [--pasta <runs/...>] [--paralelo <n>]
"""

import argparse
import hashlib
from http.client import HTTPException
import json
import os
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
CODE = HERE / "../../../../architectures"
URL = "https://openrouter.ai/api/v1/chat/completions"

# Só IPv4: em rede com IPv6 quebrado, cada chamada esperava o IPv6 falhar
_resolve = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *rest: _resolve(host, port, socket.AF_INET, *rest)

EXECUTIONS = 3
BATCH = 15  # <--- MODIFICADO 1: De 10 para 15 (envia todas as 15 perguntas de uma vez)
MAX_ROUNDS = 40
MAX_LINES = 200
MAX_MATCHES = 60
RETRIES = 6
SKIP = {"node_modules", ".git", "dist", "build", ".angular", "coverage"}

TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "Lista arquivos e pastas de um diretório do repositório.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Lê as linhas start a end (no máximo 200) de um arquivo, numeradas.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search",
        "description": "Busca uma expressão regular nos arquivos sob path; devolve arquivo:linha: trecho.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
]


# --------------------------------------------------------------- ferramentas

class Repository:
    """O código de um sistema, só para leitura, sem sair da raiz."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, path: str) -> Path:
        target = (self.root / (path or ".").lstrip("/")).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("fora do repositório")
        return target

    def list_dir(self, path: str = ".") -> str:
        target = self._path(path)
        entries = sorted(item.name + ("/" if item.is_dir() else "") for item in target.iterdir() if item.name not in SKIP)
        return "\n".join(entries) or "(vazio)"

    def read_file(self, path: str, start: int = 1, end: int | None = None) -> str:
        lines = self._path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start or 1))
        end = min(len(lines), int(end or start + MAX_LINES - 1), start + MAX_LINES - 1)
        body = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
        return body + (f"\n... ({len(lines)} linhas no arquivo)" if end < len(lines) else "")

    def search(self, pattern: str, path: str = ".") -> str:
        expression = re.compile(pattern)
        found = []
        for file in sorted(self._path(path).rglob("*")):
            if not file.is_file() or any(part in SKIP for part in file.parts) or file.stat().st_size > 1_000_000:
                continue
            try:
                lines = file.read_text(encoding="utf-8", errors="strict").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, 1):
                if expression.search(line):
                    found.append(f"{file.relative_to(self.root)}:{number}: {line.strip()[:200]}")
                    if len(found) >= MAX_MATCHES:
                        return "\n".join(found) + f"\n... (parou em {MAX_MATCHES} resultados)"
        return "\n".join(found) or "(nada encontrado)"

    def run(self, name: str, arguments: dict) -> str:
        try:
            return getattr(self, name)(**arguments)
        except Exception as error:
            return f"erro: {error}"


# --------------------------------------------------------------- prompts

def system_prompt() -> str:
    text = (HERE / "template.md").read_text(encoding="utf-8")
    body = text[text.index("## System"):text.index("## User")]
    lines = [line for line in body.splitlines() if not line.startswith("## System") and line.strip() != "---"]
    return "\n".join(lines).strip()


# <--- MODIFICADO 2: Monta o prompt usando 'id', 'campo' e 'pergunta' do meu_formulario.json
def user_prompt(system: str, batch: list[dict]) -> str:
    items = "\n".join(f"{item['id']} | {item['campo']} | {item['pergunta']}" for item in batch)
    return f"Sistema: {system}\n\nPerguntas a responder:\n{items}"


# --------------------------------------------------------------- sessão

def assemble(response) -> dict:
    """Junta os pedaços do streaming numa resposta igual à de uma chamada sem streaming."""

    message = {"role": "assistant", "content": ""}
    calls: dict[int, dict] = {}
    result: dict = {}

    for raw in response:

        line = raw.decode("utf-8").strip()

        if not line.startswith("data: ") or line == "data: [DONE]":
            continue

        chunk = json.loads(line[6:])

        if "error" in chunk:
            return {"error": chunk["error"]}

        for key in ("model", "provider", "usage"):
            if chunk.get(key):
                result[key] = chunk[key]

        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            message["content"] += delta.get("content") or ""
            for call in delta.get("tool_calls") or []:
                slot = calls.setdefault(call.get("index", 0), {"id": "", "type": "function",
                                                               "function": {"name": "", "arguments": ""}})
                slot["id"] = call.get("id") or slot["id"]
                slot["function"]["name"] += (call.get("function") or {}).get("name") or ""
                slot["function"]["arguments"] += (call.get("function") or {}).get("arguments") or ""

    if calls:
        message["tool_calls"] = [calls[index] for index in sorted(calls)]

    return dict(result, choices=[{"message": message}])


def http(body: dict) -> dict:
    """Uma chamada; limite de taxa, erro do servidor e demora são tentados de novo, com espera crescente."""

    request = urllib.request.Request(URL, data=json.dumps(dict(body, stream=True)).encode(), headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
    })

    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return assemble(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500 or attempt == RETRIES:
                raise
        except (OSError, HTTPException):
            if attempt == RETRIES:
                raise
        time.sleep(15 * 2 ** attempt)


def parameters(model: str, provider: str | None = None) -> dict:
    chosen = {"model": model, "reasoning": {"effort": "high"}, "max_tokens": 16000,
              "usage": {"include": True}, "tools": TOOLS}
    if model == "openai/gpt-5":
        chosen["provider"] = {"order": ["openai"], "allow_fallbacks": False}
    if provider:
        chosen["provider"] = {"order": [provider], "allow_fallbacks": False}
    return chosen


def answers(text: str) -> dict[str, dict]:
    found = {}
    for line in (text or "").splitlines():
        line = line.strip().strip("`")
        if line.startswith("{"):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in item:
                found[item["id"]] = item
    return found


# <--- MODIFICADO 3: Verifica se todas as perguntas (Q01..Q15) têm o campo "resposta" preenchido
def check(batch: list[dict], found: dict[str, dict]) -> str | None:
    missing = [item["id"] for item in batch if item["id"] not in found]
    if missing:
        return f"sem resposta: {missing}"
    bad = [key for key, value in found.items() if not str(value.get("resposta", "")).strip()]
    if bad:
        return f"resposta vazia: {bad}"
    return None


class Unfinished(RuntimeError):
    """A sessão não terminou; leva a conversa até ali para o registro."""

    def __init__(self, message: str, partial: dict):
        super().__init__(message)
        self.partial = partial


def session(repository: Repository, system: str, user: str, chosen: dict) -> dict:
    """Uma conversa até o modelo responder sem chamar ferramenta."""

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    calls = 0

    for round_ in range(MAX_ROUNDS + 1):

        body = dict(chosen, messages=messages)

        # No limite, sem ferramentas: o modelo tem de responder com o que já leu.
        if round_ == MAX_ROUNDS:
            messages.append({"role": "user", "content":
                             "Limite de consultas atingido. Responda agora, no formato JSON por linha pedido, "
                             "com o que já leu; se não conseguiu confirmar algo, explicite na resposta."})
            body = dict(chosen, messages=messages, tool_choice="none")

        partial = {"messages": messages, "usage": usage, "tool_calls": calls}

        try:
            response = http(body)
        except Exception as error:
            raise Unfinished(repr(error), partial)

        if "choices" not in response:
            raise Unfinished(json.dumps(response.get("error", response))[:500], partial)

        for key in usage:
            usage[key] += (response.get("usage") or {}).get(key) or 0

        message = response["choices"][0]["message"]
        messages.append({key: message[key] for key in ("role", "content", "tool_calls") if message.get(key) is not None})

        if not message.get("tool_calls"):
            return {"messages": messages, "usage": usage, "tool_calls": calls,
                    "model": response.get("model"), "provider": response.get("provider"),
                    "content": message.get("content") or ""}

        for call in message["tool_calls"]:
            calls += 1
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": repository.run(call["function"]["name"], arguments)})

    raise Unfinished(f"passou de {MAX_ROUNDS} rodadas sem responder",
                     {"messages": messages, "usage": usage, "tool_calls": calls})


def slug(model: str) -> str:
    return model.replace("/", "-").replace(":", "-")


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--repos", help="caminho da pasta com os repositórios (padrão: ../../../../architectures)")
    parser.add_argument("--only", help="nome da pasta do repositório específico")
    parser.add_argument("--execucao", type=int)
    parser.add_argument("--provider", help="fixa um provedor do OpenRouter, sem alternativa")
    parser.add_argument("--pasta", help="pasta em runs/ (padrão: o nome do modelo)")
    parser.add_argument("--paralelo", type=int, default=1, help="sessões ao mesmo tempo")
    arguments = parser.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("defina OPENROUTER_API_KEY")

    code_root = Path(arguments.repos).resolve() if arguments.repos else CODE.resolve()

    system = system_prompt()
    template_hash = hashlib.sha256((HERE / "template.md").read_bytes()).hexdigest()
    chosen = parameters(arguments.model, arguments.provider)

    # <--- MODIFICADO 4: Lê meu_formulario.json em vez de amostra.csv
    with (HERE / "meu_formulario.json").open(encoding="utf-8") as handle:
        questions = json.load(handle)["perguntas"]

    if arguments.only:
        systems = [arguments.only]
    else:
        systems = [d.name for d in sorted(code_root.iterdir()) if d.is_dir() and not d.name.startswith(".")]

    folder = HERE / "runs" / (arguments.pasta or slug(arguments.model))
    jobs = []

    for name in systems:

        for execution in range(1, EXECUTIONS + 1):

            if arguments.execucao and execution != arguments.execucao:
                continue

            seed = f"{name}-{execution}"
            order = questions[:]
            random.Random(seed).shuffle(order)

            for start in range(0, len(order), BATCH):
                number = start // BATCH + 1
                record = folder / name / f"execucao-{execution}-lote-{number:02d}.json"
                if not (record.exists() and json.loads(record.read_text()).get("ok")):
                    jobs.append((code_root, name, execution, number, seed, order[start:start + BATCH], record))

    def run(job) -> None:

        base_dir, name, execution, number, seed, batch, record = job
        started = datetime.now(timezone.utc).isoformat()

        try:
            result = session(Repository(base_dir / name), system, user_prompt(name, batch), chosen)
            found = answers(result["content"])
            problem = check(batch, found)
        except Unfinished as error:
            result, found, problem = error.partial, {}, str(error)

        record.parent.mkdir(parents=True, exist_ok=True)
        # <--- MODIFICADO 5: Salva na chave "respostas" (em vez de "verdicts")
        record.write_text(json.dumps({
            "ok": problem is None, "problem": problem, "started": started,
            "system": name, "execution": execution, "batch": number, "seed": seed,
            "items": [item["id"] for item in batch], "respostas": found,
            "parameters": {key: value for key, value in chosen.items() if key != "tools"},
            "template_sha256": template_hash, **result,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        usage = result.get("usage") or {}
        print(f"{'ok' if problem is None else 'FALHOU'} {name} exec {execution} lote {number}: "
              f"{result.get('tool_calls', 0)} ferramentas, US$ {usage.get('cost', 0):.4f}"
              + (f" — {problem}" if problem else ""), flush=True)

    with ThreadPoolExecutor(max_workers=arguments.paralelo) as pool:
        list(pool.map(run, jobs))

if __name__ == "__main__":
    main()