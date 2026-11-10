"""
LLM as a judge, o que faltou: as ocorrências que as regras do DAMFE não
detectaram, dada a reconstrução corrigida.

Uso:
  export OPENROUTER_API_KEY=...
  python3 faltou.py --model <id> [--only <sistema>] [--execucao <n>] [--dry-run]

Uma chamada por sistema e execução, registrada em
`runs-faltou/<modelo>/<sistema>/execucao-<n>.json`; chamada já
registrada com sucesso é pulada. O prompt está em `template-faltou.md`,
com as definições de `template.md`.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_judge import http, URL, slug

HERE = Path(__file__).parent
ARTIFACTS = HERE / "../reconstrucao-corrigida"
RUNS = HERE / "runs-faltou"
EXCLUDED = {"nabstore", "halloween"}
EXECUTIONS = 3
RETRIES = 8
PATTERNS = {
    "cyclic-dependency", "hub-like-dependency", "hammering-apis", "global-state-communication",
    "one-for-all", "mega-frontend", "nano-frontend",
}


def system_prompt() -> str:

    definitions = (HERE / "template.md").read_text(encoding="utf-8")
    definitions = definitions[definitions.index("### Definições"):definitions.index("### Artefatos")].strip()

    text = (HERE / "template-faltou.md").read_text(encoding="utf-8")
    body = text[text.index("## System") + len("## System"):text.index("## User")]
    body = "\n".join(line for line in body.splitlines() if line.strip() != "---").strip()

    return body.replace("{{definicoes}}", definitions)


def load(system: str, name: str):
    return json.loads((ARTIFACTS / system / f"{name}.json").read_text(encoding="utf-8"))


def compact(system: str) -> dict:
    """Os artefatos no formato do prompt: o mesmo para todos os sistemas."""

    units = [
        {
            "id": unit["id"], "role": unit.get("role"), "routes": unit.get("routes"), "mounts": unit.get("mounts"),
            "screens": [
                {"component": screen["component"], "route": screen.get("route"), "reachable": screen.get("reachable")}
                for screen in unit.get("screens") or []
            ],
            "fragments": [fragment["name"] for fragment in unit.get("fragments") or []],
            "size": unit.get("size"),
        }
        for unit in load(system, "microfrontends")
    ]

    compositions = [
        {"consumer": item["consumer"], "provider": item["provider"], "fragment": item["fragment"],
         "renders": [{"screens": render.get("screens"), "fragments": render.get("fragments")} for render in item.get("renders") or []]}
        for item in load(system, "compositions")
    ]

    navigations = [
        {"source": item["source"], "target": item["target"], "resolved_url": item.get("resolved_url"), "on": item.get("on")}
        for item in load(system, "navigations")
    ]

    communications = [
        {"source": item["source"], "target": item["target"], "channel": item.get("channel"), "mechanism": item.get("mechanism")}
        for item in load(system, "communications") if item.get("directed")
    ]

    calls: dict[str, set] = {}
    for item in load(system, "api_calls"):
        calls.setdefault(f"{item['method']} {item['path']}", set()).add(item["microfrontend"])

    state: dict[str, dict] = {}
    for item in load(system, "state_accesses"):
        state.setdefault(f"{item['library']}:{item['path']}", {}).setdefault(item["access"], set()).add(item["microfrontend"])

    return {
        "microfrontends": units,
        "compositions": compositions,
        "navigations": navigations,
        "communications": communications,
        "api_calls": {key: sorted(value) for key, value in sorted(calls.items())},
        "state_accesses": {key: {access: sorted(names) for access, names in sorted(value.items())} for key, value in sorted(state.items())},
    }


def detected(system: str) -> list[str]:

    lines = []

    for item in load(system, "detections"):
        endpoint = (item.get("metadata") or {}).get("path") or ""
        lines.append(f"- {item['anti_pattern']} | {', '.join(item.get('subjects') or [])} | {endpoint}")

    return lines or ["- (nenhum)"]


def user_prompt(system: str) -> str:

    parts = [f"Sistema: {system}", "", "Detectados pela ferramenta:", *detected(system), ""]

    for name, value in compact(system).items():
        parts += [f"{name}: {json.dumps(value, ensure_ascii=False)}", ""]

    return "\n".join(parts)


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
        elif item.get("anti_padrao") or "anti_padrao" in item:
            found.append(item)

    return found, finished


def check(found: list[dict], finished: bool) -> str | None:
    if not finished:
        return "sem a linha de fim"
    bad = [item for item in found if item.get("anti_padrao") not in PATTERNS or not item.get("micro_frontends")]
    return f"ocorrências sem anti-padrão válido ou sem micro frontend: {len(bad)}" if bad else None


def parameters(model: str) -> dict:
    return {"model": model, "reasoning": {"effort": "high"}, "max_tokens": 16000, "usage": {"include": True}}


def recheck(record: Path) -> bool:
    """Confere de novo, com as regras atuais, a última resposta gravada de uma chamada que falhou."""

    data = json.loads(record.read_text())
    last = (data.get("attempts") or [{}])[-1]
    if not last.get("content"):
        return False
    found, finished = answers(last["content"])
    last["missing"], last["problem"] = found, check(found, finished)
    data["ok"] = last["problem"] is None
    if data["ok"]:
        last["rechecked"] = datetime.now(timezone.utc).isoformat()
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data["ok"]


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--only")
    parser.add_argument("--execucao", type=int)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    systems = sorted(
        folder.name for folder in ARTIFACTS.iterdir()
        if folder.is_dir() and folder.name not in EXCLUDED and (not arguments.only or folder.name == arguments.only)
    )

    system = system_prompt()

    if arguments.dry_run:
        for name in systems:
            print(f"{name}: {len(system) + len(user_prompt(name))} caracteres")
        return

    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("defina OPENROUTER_API_KEY")

    template_hash = hashlib.sha256((HERE / "template-faltou.md").read_bytes() + (HERE / "template.md").read_bytes()).hexdigest()
    chosen = parameters(arguments.model)

    for name in systems:

        user = user_prompt(name)

        for execution in range(1, EXECUTIONS + 1):

            if arguments.execucao and execution != arguments.execucao:
                continue

            record = RUNS / slug(arguments.model) / name / f"execucao-{execution}.json"

            if record.exists() and (json.loads(record.read_text()).get("ok") or recheck(record)):
                continue

            attempts = []

            for attempt in range(RETRIES + 1):

                started = datetime.now(timezone.utc).isoformat()

                try:
                    response = http("POST", URL, dict(chosen, messages=[
                        {"role": "system", "content": system}, {"role": "user", "content": user}]))
                    if "choices" not in response:
                        raise RuntimeError(json.dumps(response.get("error", response))[:500])
                except Exception as error:  # sobrecarga, limite, rede: tenta de novo
                    attempts.append({"started": started, "error": repr(error)})
                    time.sleep(min(60 * (attempt + 1), 300))
                    continue

                message = response["choices"][0]["message"]
                found, finished = answers(message.get("content") or "")
                attempts.append({
                    "started": started, "id": response.get("id"), "model": response.get("model"),
                    "provider": response.get("provider"), "usage": response.get("usage"),
                    "content": message.get("content"), "reasoning": message.get("reasoning"),
                    "missing": found, "problem": check(found, finished),
                })

                if attempts[-1]["problem"] is None:
                    break

            ok = attempts[-1].get("problem", "erro") is None
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps({
                "ok": ok, "system": name, "execution": execution, "template_sha256": template_hash,
                "parameters": chosen, "system_prompt": system, "user": user, "attempts": attempts,
            }, ensure_ascii=False, indent=1), encoding="utf-8")

            print(f"{'ok' if ok else 'FALHOU'} {name} exec {execution}: "
                  f"{len(attempts[-1].get('missing') or [])} ocorrências", flush=True)


if __name__ == "__main__":
    main()
