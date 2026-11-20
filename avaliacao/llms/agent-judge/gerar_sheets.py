import json, pathlib, csv

pasta_runs = pathlib.Path('runs')
if not pasta_runs.exists():
    print("[ERRO] Pasta 'runs' ainda não encontrada.")
    exit(1)

arquivos = sorted(pasta_runs.rglob('*.json'), key=lambda p: p.parent.name)
print(f"Total de ficheiros JSON encontrados: {len(arquivos)}")

dados_detalhados = []
dados_matriz = {}

for f in arquivos:
    if 'execucao' not in f.name.lower() and 'exec' not in str(f).lower():
        continue

    try:
        conteudo = json.loads(f.read_text(encoding='utf-8', errors='ignore'))
    except Exception:
        continue

    repo_nome = conteudo.get('system') or conteudo.get('repo') or f.parent.name

    respostas_raw = None
    for chave in ['respostas', 'answers', 'verdicts', 'results', 'resultado']:
        if chave in conteudo and conteudo[chave]:
            respostas_raw = conteudo[chave]
            break

    if not respostas_raw:
        respostas_raw = {k: v for k, v in conteudo.items() if k.startswith('Q') and k[1:3].isdigit()}

    if not respostas_raw:
        continue

    if repo_nome not in dados_matriz:
        dados_matriz[repo_nome] = {}

    total_perguntas = 0

    if isinstance(respostas_raw, dict):
        for k in sorted(respostas_raw.keys()):
            val = respostas_raw[k]
            if isinstance(val, dict):
                campo = val.get('campo') or val.get('pergunta') or ''
                resposta = val.get('resposta') or val.get('answer') or val.get('verdict') or ''
                evidencia = val.get('evidencia') or val.get('evidence') or ''
            else:
                campo = ''
                resposta = str(val)
                evidencia = ''

            if isinstance(evidencia, list):
                evidencia = "; ".join(str(e) for e in evidencia)

            dados_detalhados.append({
                'repositorio': repo_nome,
                'id': k,
                'pergunta': campo,
                'resposta': resposta,
                'evidencia': evidencia
            })
            dados_matriz[repo_nome][k] = resposta
            total_perguntas += 1

    elif isinstance(respostas_raw, list):
        for idx, item in enumerate(respostas_raw, start=1):
            if isinstance(item, dict):
                k = item.get('id') or item.get('qid') or f"Q{idx:02d}"
                campo = item.get('campo') or item.get('pergunta') or ''
                resposta = item.get('resposta') or item.get('answer') or ''
                evidencia = item.get('evidencia') or item.get('evidence') or ''
                if isinstance(evidencia, list):
                    evidencia = "; ".join(str(e) for e in evidencia)
                dados_detalhados.append({
                    'repositorio': repo_nome,
                    'id': k,
                    'pergunta': campo,
                    'resposta': resposta,
                    'evidencia': evidencia
                })
                dados_matriz[repo_nome][k] = resposta
                total_perguntas += 1

    print(f" -> Processado: {repo_nome} ({total_perguntas} perguntas)")

with open('extracao_matriz_google_sheets.csv', 'w', newline='', encoding='utf-8-sig') as f:
    colunas = ['repositorio'] + [f"Q{i:02d}" for i in range(1, 16)]
    writer = csv.writer(f, delimiter=',')
    writer.writerow(colunas)
    for repo_nome in sorted(dados_matriz.keys()):
        linha = [repo_nome] + [dados_matriz[repo_nome].get(f"Q{i:02d}", "-") for i in range(1, 16)]
        writer.writerow(linha)

with open('extracao_detalhada_google_sheets.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=['repositorio', 'id', 'pergunta', 'resposta', 'evidencia'], delimiter=',')
    writer.writeheader()
    writer.writerows(dados_detalhados)

print(f"\n[SUCESSO] Concluído! {len(dados_matriz)} repositórios gravados com sucesso.")
