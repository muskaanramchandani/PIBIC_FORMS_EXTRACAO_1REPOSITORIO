import json, pathlib

ficheiros = sorted(pathlib.Path('runs').rglob('*.json'), key=lambda p: p.parent.name)

# Dicionario para guardar o json mais recente de cada repositorio valido
repos = {}
for f in ficheiros:
    try:
        dados = json.loads(f.read_text(encoding='utf-8'))
        if 'respostas' in dados and len(dados['respostas']) > 0:
            nome_repo = dados.get('system', f.parent.name)
            repos[nome_repo] = dados['respostas']
    except Exception:
        continue

linhas = []
linhas.append("=" * 70)
linhas.append("RELATÓRIO DE EXTRAÇÃO ARQUITETURAL - 15 PERGUNTAS")
linhas.append(f"Total de Repositórios Analisados: {len(repos)}")
linhas.append("=" * 70 + "\n\n")

for i, (repo_nome, respostas) in enumerate(sorted(repos.items()), start=1):
    linhas.append("#" * 70)
    linhas.append(f"REPOSITÓRIO {i}: {repo_nome}")
    linhas.append("#" * 70 + "\n")
    
    for k in sorted(respostas.keys()):
        item = respostas[k]
        campo = item.get('campo', 'Questão')
        resposta = item.get('resposta', 'Sem resposta')
        evidencia = item.get('evidencia', 'Nenhuma evidência citada')
        
        linhas.append(f"Pergunta: {k} - {campo}")
        linhas.append(f"Resposta: {resposta}")
        linhas.append(f"Evidência: {evidencia}")
        linhas.append("")  # Espaço em branco entre as questões
    
    linhas.append("\n" + "-" * 70 + "\n\n")

conteudo_final = "\n".join(linhas)

pathlib.Path("relatorio_formatado.txt").write_text(conteudo_final, encoding="utf-8")
print(f"Relatório gerado com sucesso para {len(repos)} repositórios em: relatorio_formatado.txt")
