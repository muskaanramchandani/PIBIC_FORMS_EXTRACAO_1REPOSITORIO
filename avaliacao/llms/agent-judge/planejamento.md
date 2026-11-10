# Agent as a judge — planejamento

Um agente com acesso de leitura ao código confere se a arquitetura que o DAMFE reconstruiu está certa. Mede a **reconstrução**, não os anti-padrões. Prompt em [`template.md`](template.md).

## Para quê

- **Precisão da extração**, por tipo de item: dos itens extraídos, quantos o código confirma.
- **O que faltou**: em MFEs sorteados, o que o DAMFE deveria ter extraído e não extraiu.
- **Estabilidade do agente**: concordância entre as 3 execuções.

## Agente

Laço próprio (`run_agent.py`) pelo **OpenRouter**: o modelo recebe três ferramentas só de leitura, restritas à pasta do código do sistema, e as usa até fechar os vereditos.

| ferramenta | o que faz | limite |
|---|---|---|
| `list_dir` | lista uma pasta | ignora `node_modules`, `.git`, `dist`, `build`, `.angular`, `coverage` |
| `read_file` | lê um trecho, com número de linha | 200 linhas por chamada |
| `search` | busca um padrão no código | 60 resultados por chamada |

## Modelos

Critérios: **chamada de ferramentas** (sem ela o modelo não abre o código); **raciocínio**; **contexto longo**, porque a conversa cresce a cada arquivo lido e é reenviada a cada rodada (em média, de 57 a 180 mil tokens de entrada por sessão, somadas as rodadas); **família diferente** do Claude; e **custo**. O agente gasta de 2,7 a 8,4 M tokens por execução: a 1ª execução dos pagos coube no saldo inicial, e a 2ª e 3ª vieram com crédito extra, priorizadas sobre o LLM-as-a-judge.

| modelo | contexto | ferramentas / raciocínio | execuções | provedor | por quê |
|---|---|---|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 1 M (gratuito); 262 mil (DeepInfra) | sim / sim | 3 | Nvidia, gratuito (74 sessões); DeepInfra, pago e fixado (67) | gratuito e aberto, com 1 M de contexto; quando a cota gratuita do dia acabou, o mesmo modelo pago, para não trocar de juiz no meio |
| `deepseek/deepseek-v4-pro` | 1 M | sim / sim | 3 | Baidu: escolhido pelo OpenRouter na 1ª execução, fixado na 2ª e 3ª para não mudar de provedor entre execuções | segundo juiz, outra família; o mais barato entre os pagos fortes (US$ 0,96 / 1,91 por M) |
| `openai/gpt-5-mini` | 400 mil | sim / sim | 3 | OpenAI | terceiro juiz, da linhagem GPT dos estudos de LLM-as-a-judge; cabia no saldo (US$ 0,25 / 2 por M) |

Provedores do DeepSeek: o Parasail, fixado primeiro, devolvia limite de taxa e era lento (descartado, em `descartados/`); o DeepInfra também devolveu limite de taxa; sem fixar, o OpenRouter mandou tudo para o Baidu. O provedor de cada sessão fica no registro.

## Parâmetros

| parâmetro | valor | por quê |
|---|---|---|
| `reasoning.effort` | `high`, em todos | conferir uma afirmação no código pede seguir chamadas entre arquivos; o mesmo nível em todos deixa a comparação justa |
| `max_tokens` | 16.000 por rodada | cabe o raciocínio e a resposta final de 10 itens |
| rodadas | até 40 por sessão | ~4 chamadas de ferramenta por item, folga sobre o que os modelos usaram (ex.: 26 no lote do Bahmni, no gpt-5-mini); passando disso a sessão é refeita |
| temperatura, `top_p` | não enviados: vale o padrão de cada modelo | o gpt-5-mini não aceita temperatura; Nemotron usa 1 e `top_p` 0,95; DeepSeek, 1 e 1 (padrões informados pelo OpenRouter) |
| `seed` | não usado | os modelos não garantem reprodução por semente; a ordem dos itens tem semente própria (`<sistema>-<execução>`) |
| streaming | ligado | sem ele a conexão caía em ~100 s quando o modelo pensava muito |
| tentativas | até 6, com espera de 15 s × 2ⁿ, em limite de taxa, erro do servidor, queda ou timeout | rodadas longas, em horário de pico |
| `timeout` | 600 s por chamada | |
| rede | só IPv4 | o IPv6 da rede quebrou durante a rodada |
| paralelo | 4 sessões ao mesmo tempo | encurtar a rodada; as sessões não compartilham estado |
| resposta | JSON por item, conferido: todos os ids, veredito válido | sessão com item faltando é refeita inteira |

Considerados e não usados:

| modelo | por quê não |
|---|---|
| Gemini CLI (Gemini Pro) | era o plano inicial; a CLI estava logada na conta corporativa, com a cota esgotada, e usar a licença da empresa numa pesquisa não era apropriado |
| Claude (Opus, Sonnet) | mesma família de quem ajudou a construir o DAMFE: o juiz poderia favorecê-lo |
| `openai/gpt-5`, `gpt-5.6-sol` | US$ 5 a 12 por execução, acima do orçamento |
| `openai/gpt-5.6-luna`, `gpt-oss-120b` | mais baratos que o gpt-5-mini, mas preferimos o da mesma família do GPT-5 |

## Amostra

Fórmula de Cochran para proporção, com correção para população finita: n₀ = z²·p(1−p)/e², n = n₀ / (1 + (n₀−1)/N), com **95% de confiança** (z = 1,96; vale para todo intervalo do estudo), p = 0,5 (o caso mais conservador) e **margem de erro de 10% por tipo**.

| tipo | itens extraídos (N) | amostra |
|---|---|---|
| micro frontend | 106 | 51 |
| tela | 341 | 76 |
| fragmento | 36 | 27 |
| composição | 25 | 21 |
| navegação | 47 | 32 |
| comunicação (direcionada) | 45 | 31 |
| chamada de API | 2.059 | 92 |
| acesso a estado | 846 | 87 |
| **total** | **3.505** | **417** |

Dentro de cada tipo, a amostra é repartida entre os sistemas na proporção dos itens de cada um (no mínimo 1 onde houver), e sorteada com semente registrada.

**O que faltou:** um MFE sorteado por sistema; o agente procura no código o que deveria ter sido extraído dele e não foi.

## Como roda

| | |
|---|---|
| lotes | 10 itens por sessão, do mesmo sistema |
| repetição | 3 execuções por modelo, em sessões separadas; vale a maioria por item |
| ordem | itens embaralhados a cada execução, antes de formar os lotes; semente registrada |
| sessões | 47 lotes por execução (141 nas 3), mais 12 por execução de "o que faltou" |
| veredito | `correto`, `parcial`, `incorreto` ou `nao_verificavel`, sempre com `arquivo:linha` lido |

## O que faltou (parte 2, 15/10/2026)

Mede a revocação da reconstrução: um MFE sorteado por sistema (semente `faltou-<sistema>`, em [`faltou/amostra.csv`](faltou/amostra.csv)), nos 10 sistemas sem nabstore e halloween. O agente recebe o que o DAMFE extraiu dele e procura no código o que ficou de fora; termina com `{"fim": true}`, que separa "não falta nada" de resposta cortada. Parte da **reconstrução corrigida** ([`../reconstrucao-corrigida/`](../reconstrucao-corrigida/), DAMFE `f88ae29`), para medir o que ainda falta. Roda com [`faltou.py`](faltou.py); registro em `runs-faltou/<modelo>/<sistema>/execucao-<n>.json`. Toda omissão apontada é conferida no código antes de contar, como nos achados.

**Modelos:** os mesmos juízes da parte 1. Primeiro o gratuito, `nvidia/nemotron-3-ultra-550b-a55b:free`; com crédito, DeepSeek e gpt-5-mini (decisão de 15/10: ver se o resultado vale antes de gastar). Antes, foram testados outros gratuitos para completar três famílias sem custo, e descartados (registros em `descartados/faltou-*`): `thinkingmachines/inkling:free` só funciona em agentes de código cadastrados (403); `cohere/north-mini-code:free` falhou em 5 de 7 sessões (resposta vazia, tipo fora da lista); `poolside/laguna-s-2.1:free` fez 2 sessões em 2 h; `dots-studio/dots-3-note-preview:free` andava, mas fica fora para os juízes serem os mesmos da parte 1. Os gratuitos ficam sobrecarregados por períodos; a sessão recomeça até 8 vezes, com espera crescente.

**Cobertura:** sessão que falhou foi refeita uma vez, com os mesmos parâmetros. Ficaram válidas 29 de 30 do DeepSeek e 24 de 30 do gpt-5-mini; o gpt-5-mini chega ao limite de 40 rodadas e devolve resposta vazia ou cortada, e no pagopa e no topcoder ficou com uma sessão só (sem maioria possível). O Nemotron não completou nenhuma: a NVIDIA respondeu "sobrecarregado" (503) durante todo o período. Uma omissão conta quando aparece em 2 das 3 execuções do modelo (mesmo tipo e evidência no mesmo arquivo, a até 3 linhas), por [`faltou_resumo.py`](faltou_resumo.py), em [`faltou/omissoes.csv`](faltou/omissoes.csv); a conferência no código está em `faltou/conferencia-<sistema>.csv`. Custo nos registros: US$ 3,91 (DeepSeek) e US$ 2,06 (gpt-5-mini); o saldo caiu US$ 6,46 com a parte LLM, porque a sessão refeita sobrescreve o registro da que falhou.

**Amostra extra do udistrital (15/10):** 1 de 53 MFEs era pouco para o maior sistema. Mais 10, sem repetir o primeiro (semente `faltou-udistrital-mais`, em [`faltou/amostra-udistrital.csv`](faltou/amostra-udistrital.csv)), só com o gpt-5-mini, pelo saldo (decisão de 15/10); registro em `runs-faltou/openai-gpt-5-mini/udistrital/<diretório>/`. Duas mudanças no prompt para isso: o MFE é achado pelo diretório (os 7 shells do udistrital saem com o mesmo id; defeito #26 em `correcoes-reconstrucao.md`), e cada comunicação mostra até 4 locais e quantos ficaram de fora (um canal de storage tinha centenas, e o prompt chegava a 373 mil caracteres). As execuções rodam na ordem 1, 2, 3, e param se o saldo cair abaixo de US$ 0,40.

## Registro

Por sessão, em `runs/<modelo>/<sistema>/execucao-<n>-lote-<k>.json`: modelo e provedor devolvidos pelo OpenRouter, data e hora, a semente, o prompt, as chamadas de ferramenta, a resposta, tokens e custo.

## Ameaças à validade mitigadas

| tipo | ameaça | mitigação |
|---|---|---|
| construto | **o agente julgar o que o item "deveria" ser**, não o que ele afirma | o prompt define o que cada tipo de item afirma; o veredito é sobre essa afirmação |
| interna | **alucinação** (afirmar que leu o que não leu) | toda conclusão exige `arquivo:linha` lido; os citados podem ser conferidos |
| interna | **viés de concordância** com o DAMFE | o veredito tem quatro opções, inclusive `parcial` e `nao_verificavel`; o agente procura no código, não confirma o item |
| interna | **não determinismo** | 3 execuções em sessões separadas, com a maioria por item |
| interna | **viés de posição** | itens embaralhados a cada execução, e os lotes mudam junto |
| interna | **o agente mexer no repositório** ou seguir instruções escritas no código | as ferramentas só leem, dentro da pasta do sistema; o prompt manda tratar o conteúdo do repositório como dado |
| conclusão | **amostra pequena demais** para algum tipo | tamanho calculado por tipo, com margem de erro declarada |
| conclusão | **amostra dominada por um sistema** | repartida entre os sistemas na proporção de cada um |
| confiabilidade | **resultado não reproduzível** | registro de cada sessão; semente da amostra e da ordem |
| independência | **o juiz ser da mesma família de quem ajudou a construir o DAMFE** (Claude) | três juízes de outras famílias (NVIDIA, DeepSeek, OpenAI) |
| conclusão | **o resultado depender de um modelo só** | três modelos, com a concordância entre eles medida |

## Dúvidas

1. Margem de erro de 10% por tipo (417 itens) ou de 5% (994 itens, mais que o dobro de sessões)?
