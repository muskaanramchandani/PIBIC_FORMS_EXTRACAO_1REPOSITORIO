import json, pathlib

arquivos = list(pathlib.Path('runs').rglob('*micro-frontends*/*.json')) + list(pathlib.Path('runs').rglob('*micro-frontends*.json'))

if not arquivos:
    print("Nenhum resultado encontrado para micro-frontends.")
else:
    f = arquivos[0]
    conteudo = json.loads(f.read_text(encoding='utf-8'))
    print(f"\n==========================================")
    print(f"Repositório: micro-frontends")
    print(f"Arquivo lido: {f}")
    print(f"==========================================\n")
    data = conteudo.get('respostas', {})
    for k in sorted(data):
        v = data[k]
        print(f"=== {k}: {v.get('campo')} ===")
        print(f"-> Resposta: {v.get('resposta')}")
        print(f"-> Evidência: {v.get('evidencia')}\n")
