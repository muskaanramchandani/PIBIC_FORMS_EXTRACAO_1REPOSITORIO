# Agent as a judge — achados

O que os vereditos `incorreto` e `parcial` apontam, conferido no código. Números por tipo e por sistema em [`resultados.md`](resultados.md) (gerado por `resultados.py`).

## Defeitos do DAMFE (confirmados no código)

| tipo | sistema | defeito | evidência |
|---|---|---|---|
| navegação | udistrital | chamada HTTP lida como navegação, porque o caminho da API coincide com a rota de outro MFE | `plan-accion.component.ts:107` (`request.get(..., '/formulacion/planes_accion')`), `documentos.service.ts:13` |
| navegação | fubaritico | rota do servidor Express lida como navegação | `apps/photos/server.js:24` (`app.get('/', ...)`) |
| navegação | fubaritico | `useMatch` (teste da rota atual) lido como ida para a rota | `HeaderSearch.tsx:20` |
| fragmento, composição | LBHackney | qualquer export vira fragmento, inclusive objeto de configuração | `mtfh-processes.tsx:10` (`export { locale, processes }`) |
| tela | pagopa | `Redirect` do react-router lido como tela, num arquivo de mock | `mock_dashboard/indexMicrofrontend.tsx:39` |
| tela | udistrital | rota sem o prefixo do módulo carregado sob demanda (`/aspirantes` em vez de `/inscripciones/aspirantes`) | 4 telas, todas `parcial` |
| tela, fragmento | vários | o local junta o arquivo do componente com a linha de onde ele é usado (rota ou export), num arquivo diferente | `Home.tsx:27`, mas a rota está em `main.tsx:27` (diego-coronado); `ProductImagemFragment/index.js:22`, mas o export está em `nabstore-mfe-products.js:22`. O DeepSeek marcou `parcial` em ~25 telas e fragmentos por isso |

## Erros do agente

- **Evento `lang` (udistrital):** o agente procurou só `addEventListener` e marcou incorreto; os MFEs escutam com `fromEvent(window, 'lang')`. O DAMFE estava certo.
- **halloween:** veredito `incorreto` com a justificativa "isso está correto". A maioria das 3 execuções corrige.

## Decidido (14/10/2026)

- `removeItem` conta como "grava" estado: **sim** (o DAMFE já fazia assim).
- O local de uma tela ou fragmento é **a definição do componente**.
- O micro frontend é identificado **pelo diretório**.
- `root.component.js` que só monta providers **não é tela**.

Os defeitos acima e estas decisões foram corrigidos no DAMFE: ver [`../../correcoes-reconstrucao.md`](../../correcoes-reconstrucao.md).

## Entre os modelos

Os três com 3 execuções; vale a maioria por item. Entre as 3 execuções, o κ é a média do κ de Cohen dos 3 pares. O κ fica baixo mesmo com concordância alta porque quase tudo é `correto`: o acaso já explica boa parte do acerto.

| | correto | parcial | incorreto | não verificável | unânimes nas 3 | κ de Cohen entre as 3 |
|---|---|---|---|---|---|---|
| Nemotron | 92% | 10 | 25 | 0 | 87% | 0,43 |
| DeepSeek | 85% | 46 | 17 | 0 | 82% | 0,58 |
| gpt-5-mini | 91% | 17 | 8 | 11 | 69% | 0,16 |

| par | mesmo veredito | κ de Cohen |
|---|---|---|
| Nemotron × DeepSeek | 375 de 420 (89%) | 0,50 |
| Nemotron × gpt-5-mini | 374 (89%) | 0,31 |
| DeepSeek × gpt-5-mini | 344 (82%) | 0,17 |

- **DeepSeek é o mais rigoroso:** 33 itens `parcial` em que o Nemotron diz `correto`, na maioria telas (59% de telas corretas, contra 86% e 89%); ele confere a linha citada (defeito do local, acima).
- **gpt-5-mini é o menos estável** (69% unânimes) e o mais leniente com exports: composição 100% e fragmento 96% corretos, aceitando os itens do LBHackney que os outros dois rejeitam. Seus `nao_verificavel` caem de 34 (uma execução) para 11 pela maioria: eram, em boa parte, desistências que não se repetem.
- **Navegação** é o tipo pior avaliado pelos três (56% a 75% corretos): os defeitos do udistrital e do fubaritico aparecem em todos.

## Execução

| modelo | execuções | sessões | provedor | custo |
|---|---|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 3 | 141 | Nvidia, gratuito (74); DeepInfra, pago (67) | US$ 2,78 |
| `deepseek/deepseek-v4-pro` | 3 | 141 | Baidu (141): escolhido pelo OpenRouter na 1ª, fixado na 2ª e 3ª | US$ 2,86 |
| `openai/gpt-5-mini` | 3 | 141 | OpenAI (141) | ~US$ 10 |

Ajustes no `run_agent.py` durante a rodada, sem mudar o prompt:
- tenta de novo, com espera crescente, quando há limite de taxa, erro do servidor ou queda de conexão;
- usa só IPv4, porque o IPv6 da rede quebrou;
- recebe a resposta em streaming, para a conexão não cair quando o modelo pensa por muito tempo;
- roda sessões em paralelo (`--paralelo`).

## O que faltou (parte 2, 15/10/2026)

Resultado em [`resultados.md`](resultados.md), seção "O que faltou".
