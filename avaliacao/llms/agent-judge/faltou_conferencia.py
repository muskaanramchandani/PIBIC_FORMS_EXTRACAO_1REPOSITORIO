"""
Junta as conferências do que faltou e aplica os mesmos critérios a todos os sistemas.

Uso: python3 faltou_conferencia.py

Lê `faltou/conferencia-<sistema>.csv` (conferência no código, item a item)
e escreve `faltou/conferencia.csv`, com o veredito final e a causa
agrupada. Três ajustes, para o critério ser um só:
- cookie conta como estado global só quando outro MFE usa a mesma chave;
- fato que só existe fora do código-fonte (spec OpenAPI que gera o
  cliente no build, URL do environment.json) é limitação da análise
  estática, não falso negativo;
- código de pacote compartilhado que o MFE importa conta para o MFE.
Itens iguais apontados pelos dois modelos contam uma vez.
"""

import csv
import re
from pathlib import Path

HERE = Path(__file__).parent / "faltou"

CAUSES = [
    ("spec OpenAPI", "limitação", "cliente HTTP gerado no build, a partir da spec OpenAPI"),
    ("environment.json", "limitação", "URL vinda inteira do arquivo de configuração de runtime"),
    ("tabela de rotas", "falso negativo", "tabela de rotas própria (objeto com path/component montado em laço)"),
    ("biblioteca compartilhada", "falso negativo", "código de pacote compartilhado que o MFE importa"),
    ("SDK gerado", "falso negativo", "código de pacote compartilhado que o MFE importa"),
    ("GraphQL", "falso negativo", "cliente GraphQL (Apollo) não reconhecido"),
    ("new URL", "falso negativo", "URL montada com new URL(...)"),
    ("ternário", "falso negativo", "URL montada com ternário na função que embrulha o cliente"),
    ("parâmetro depois", "falso negativo", "URL da função que embrulha o cliente continua depois do endpoint (`${base}${endpoint}/${id}`)"),
    ("continua depois", "falso negativo", "URL da função que embrulha o cliente continua depois do endpoint (`${base}${endpoint}/${id}`)"),
    ("campo da classe", "falso negativo", "URL lida de campo da classe (`this.environment.X`)"),
    ("membro de `this`", "falso negativo", "URL lida de campo da classe (`this.environment.X`)"),
    ("template string", "falso negativo", "destino em template string (`/movie/${id}`)"),
    ("map", "falso negativo", "destino lido de item de lista percorrida por .map"),
    ("activeWhen", "falso negativo", "dono do destino só pelo activeWhen, sem as rotas internas do MFE"),
    ("rotas do MFE de", "falso negativo", "dono do destino só pelo activeWhen, sem as rotas internas do MFE"),
    ("EJS", "falso negativo", "script inline do template HTML/EJS do shell"),
    ("clear()", "falso negativo", "localStorage.clear()"),
    ("chave de localStorage", "falso negativo", "chave de storage com trecho de runtime"),
    ("window", "falso negativo", "propriedade global de window"),
    ("cookie", "falso negativo", "document.cookie"),
    ("useSelector", "falso negativo", "useSelector reexportado com outro nome"),
]


def place(evidence: str) -> str:
    match = re.match(r"\s*(.+?):(\d+)", evidence or "")
    return f"{Path(match.group(1)).name}:{match.group(2)}" if match else evidence


def main() -> None:

    rows = []
    for path in sorted(HERE.glob("conferencia-*.csv")):
        extra = path.stem.endswith("-extra")
        for row in csv.DictReader(path.open(encoding="utf-8")):
            row["amostra"] = "extra" if extra else "principal"
            rows.append(row)

    for row in rows:
        verdict, cause = row["veredito"], ""
        text = row["causa_damfe"] + " " + row["motivo"]
        if verdict == "falso negativo":
            verdict, cause = next(((v, c) for key, v, c in CAUSES if key in text), (verdict, row["causa_damfe"]))
            # Cookie que só o próprio MFE usa não liga um MFE a outro.
            if cause == "document.cookie" and not any(mark in text for mark in ("gravado por outros MFEs", "chave gravada por")):
                verdict, cause = "fora do escopo", ""
        elif row["sistema"] == "Insta-Graph" and "módulo utilitário" in text:
            verdict, cause = "falso negativo", "código de pacote compartilhado que o MFE importa"
        row["final"], row["causa"] = verdict, cause
        row["item"] = f"{row['amostra']}|{row['sistema']}|{row['tipo']}|{place(row['evidencia'].split(';')[0])}"

    with (HERE / "conferencia.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    unique = {}
    for row in rows:
        unique.setdefault(row["item"], row)

    print(f"{len(rows)} omissões, {len(unique)} itens distintos")
    for verdict in ("falso negativo", "limitação", "fora do escopo", "já extraído", "não existe"):
        print(f"  {verdict}: {sum(1 for r in unique.values() if r['final'] == verdict)}")
    print()
    counts = {}
    for row in unique.values():
        if row["final"] in ("falso negativo", "limitação"):
            counts.setdefault((row["final"], row["causa"]), set()).add(row["sistema"])
            counts.setdefault(("n", row["final"], row["causa"]), []).append(row)
    for key, systems in sorted(counts.items(), key=lambda kv: -len(counts[("n",) + kv[0]]) if kv[0][0] != "n" else 0):
        if key[0] != "n":
            print(f"  {len(counts[('n',) + key])} | {key[0]} | {key[1]} | {', '.join(sorted(systems))}")
    print()
    for system in sorted({r["sistema"] for r in unique.values()}):
        items = [r for r in unique.values() if r["sistema"] == system]
        print(f"  {system}: {len(items)} itens, {sum(r['final'] == 'falso negativo' for r in items)} FN")


if __name__ == "__main__":
    main()
