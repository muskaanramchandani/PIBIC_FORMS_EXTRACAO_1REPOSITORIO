# Avaliação do DAMFE

Três coautores com experiência em micro frontends julgam as detecções do DAMFE. Nenhum acompanhou a definição das heurísticas.

## O que medimos

- **Concordância** entre os três (concordância % e κ de Cohen, média dos pares).
- **Precisão** por anti-padrão: das detecções, quantas a maioria confirma.
- **Por que erra**: cada falso positivo classificado em heurística, limiar, reconstrução ou definição.

Os coautores não medem revocação: só as detecções são avaliadas. A revocação é estimada pelos juízes LLM ("o que faltou"): da reconstrução no agent-judge (63 falsos negativos em 20 MFEs sorteados) e das regras no llm-judge (nano no diego-coronado e no Insta-Graph), todos conferidos no código.

## Itens (166, cerca de 3 a 4 h por pessoa)

| anti-padrão | detecções (todas avaliadas) |
|---|---|
| Hammering APIs | 120 (116 do udistrital) |
| Nano Frontend | 40 |
| Global State Communication | 3 |
| Mega Frontend | 2 |
| One Micro Frontend for All | 1 |
| Cyclic Dependency | 0 |
| Hub-like Dependency | 0 |

Cyclic e Hub-like fazem parte da avaliação, mas não dispararam nos 12 sistemas: não há item para julgar, e o artigo reporta isso.

## Como eles avaliam

Os CSVs em [`avaliacao/profissionais/`](avaliacao/profissionais/), importados numa planilha:

1. **sobre-voce.csv** — experiência com micro frontends e quais anti-padrões já viram na prática
2. **avaliacao-<sistema>.csv** — uma aba por sistema; por detecção: Sim / Não / Não sei, e justificativa quando for Não ou Não sei

Julgam pela página do DAMFE de cada sistema, com as explicações das detecções visíveis. Julgam sozinhos e só conversam depois de todos entregarem. Antes, uma reunião de 30 min com um sistema de treino.

## Decisões

- **Itens:** todas as 166 detecções, inclusive as 40 de Nano.
- **Global State:** julgado pelo sistema todo, não por fatia.
- **Página:** com as explicações do DAMFE visíveis.
- **Falsos negativos:** não se pergunta aos coautores o que o DAMFE deixou de listar; isso fica com os juízes LLM (ver acima).
- **Classificação dos erros:** eu e outro coautor, com a concordância entre nós reportada.
- **Caracterização:** só a experiência de cada avaliador, não a empresa.
