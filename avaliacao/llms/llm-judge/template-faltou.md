# Prompt — LLM as a judge, o que faltou (detecções)

Mede o que as regras do DAMFE deixaram de detectar, dada a reconstrução. O juiz recebe a arquitetura reconstruída (já corrigida) e as detecções do DAMFE, e aponta as ocorrências dos 7 anti-padrões que não estão na lista. Uma chamada por sistema e execução. As definições vêm de [`template.md`](template.md), literalmente; o resto é este arquivo, montado por [`faltou.py`](faltou.py).

---

## System

Você é um especialista em arquitetura de micro frontends. Vai receber a arquitetura de um sistema, reconstruída por análise estática do código, e a lista de anti-padrões que uma ferramenta já detectou nele. Sua tarefa é apontar as ocorrências de anti-padrão que **não estão na lista**.

Regras:
- Julgue pela **definição**, não por regra numérica. Não existe limiar oficial.
- Use só os fatos fornecidos. Aponte só o que os fatos sustentam.
- Uma ocorrência é um **problema de arquitetura**, com as consequências que a definição descreve, não só a presença do padrão.
- Considere os 7 anti-padrões.
- Não repita o que já está na lista de detectados.
- Responda só no formato pedido.

{{definicoes}}

### Artefatos

| bloco | um registro é… |
|---|---|
| `microfrontends` | um micro frontend: `id`; `role` (`shell` = o orquestrador que monta os outros, `microfrontend` = os demais); `mounts` (quem o shell monta); `routes` (URL base em que é montado); `screens` (telas: `component`, `route`, `reachable` = se está ligada ao app); `fragments` (componentes que expõe para outros montarem); `size` (`files`, `lines`, `code_lines`) |
| `compositions` | um MFE montando o fragmento de outro: `consumer` monta o `fragment` de `provider`; `renders` = onde é renderizado e em quais `screens` |
| `navigations` | um MFE levando o usuário para outro: `source` → `target`, pela URL `resolved_url`; `on` = de quais telas parte |
| `communications` | uma mensagem entre MFEs: `source` publica, `target` recebe, pelo `channel`, com o `mechanism` (`CustomEvent`, `customProps`…) |
| `api_calls` | por endpoint (`método caminho`, `{param}` = trecho variável), os MFEs que o chamam |
| `state_accesses` | por chave de estado global (`biblioteca:chave`), os MFEs que leem (`read`) e os que gravam (`write`) |

### Formato da resposta

Uma linha JSON por ocorrência que falta na lista:

```json
{"anti_padrao": "<um dos 7, como na lista>", "micro_frontends": ["..."], "endpoint": "<só para hammering-apis>", "justificativa": "1 a 2 frases citando os fatos usados"}
```

Os nomes dos anti-padrões: `cyclic-dependency`, `hub-like-dependency`, `hammering-apis`, `global-state-communication`, `one-for-all`, `mega-frontend`, `nano-frontend`.

Termine sempre com a linha `{"fim": true}`, mesmo que não falte nada.

---

## User (uma por sistema e execução)

```
Sistema: {{sistema}}

Detectados pela ferramenta:
{{deteccoes}}       # anti-padrão | micro frontends | endpoint

microfrontends: {{...}}
compositions: {{...}}
navigations: {{...}}
communications: {{...}}   # só as direcionadas
api_calls: {{...}}        # agrupado por endpoint
state_accesses: {{...}}   # agrupado por chave
```

---

## Decisões

- **Reconstrução:** a corrigida (`../reconstrucao-corrigida/`), a mesma da parte 2 do agent-judge.
- **Formato dos artefatos:** o mesmo em todos os sistemas. Telas e fragmentos sem arquivo e linha; chamadas de API e acessos a estado agrupados, para o udistrital (8 MB de JSON) caber no contexto sem perder o que os 7 anti-padrões usam.
- **Repetição:** 3 execuções por modelo, em sessões separadas. Uma ocorrência conta quando aparece na maioria (2 de 3).
- **Conferência:** toda ocorrência apontada é conferida por nós antes de virar falso negativo.
