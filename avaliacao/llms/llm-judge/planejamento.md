# LLM as a judge — planejamento

Um LLM julga as 166 detecções do DAMFE, uma por linha do CSV (`avaliacao-<sistema>.csv`), com o prompt de [`template.md`](template.md). Os coautores julgam as mesmas detecções numa planilha com 43 linhas (ver Comparação com os coautores).

## Para quê

- **Comparar com os coautores:** concordância do LLM com a maioria dos três (concordância % e κ de Cohen).
- **Quarto avaliador:** ver se o LLM concorda com os coautores tanto quanto eles concordam entre si.
- **Estabilidade:** concordância do LLM com ele mesmo, entre as 3 execuções.

## Comparação com os coautores

A planilha dos coautores (`profissionais/avaliacao.xlsx`) segue a página do DAMFE, e por isso difere do CSV dos juízes em dois pontos:

- **Sem nabstore e halloween:** não vieram da mineração (o halloween caiu no EC6, com 10 commits; o nabstore não está nela). As 6 detecções deles saem da comparação, e ficam 160.
- **Hammering agrupado:** a página junta numa linha só as detecções de rota do mesmo anti-padrão, e a planilha também. Os juízes julgaram cada rota, então as 120 linhas de Hammering viram 3 grupos (udistrital, 116 rotas; topcoder, 3; Grupo-10, 1). Ao todo, ficam 43 linhas. Nos grupos grandes, o coautor confere pelo menos 5 rotas escolhidas aleatoriamente e responde de acordo com elas; o juiz julgou todas.

**Veredito do juiz num grupo:** primeiro, a maioria das 3 execuções em cada rota, como nas outras linhas; depois, a maioria entre as rotas do grupo. Num empate, vale o veredito mais severo (Não, depois Não sei, depois Sim), como no agent-judge. As outras 40 linhas casam uma a uma, por sistema, anti-padrão e micro frontends; como a reconstrução corrigida passou a nomear cada micro frontend pelo diretório, o nome da planilha é casado com o dos juízes pelo `registered_name` dos artefatos novos (`damfe/artefatos/`). As detecções em si não mudaram com as correções (ver `correcoes-reconstrucao.md`), então os vereditos dos juízes continuam valendo. Foi escolhido juntar os vereditos que já existiam, em vez de rodar os juízes de novo nos grupos, porque não custa nada e usa as 3 execuções completas; rodar de novo também não caberia no saldo (US$ 0,31) para os três.

## Como roda

| | |
|---|---|
| entrada | os artefatos da reconstrução (os mesmos de onde sai a página dos coautores) + as linhas do CSV do lote. **Não** passa `detections.json`, que traria a explicação e o limiar do DAMFE |
| recorte | `microfrontends.json` sempre inteiro; os outros, recortados ao que as linhas do lote envolvem quando o sistema é grande (o udistrital tem ~6,7 MB). `communications.json` só com as comunicações direcionadas — as não direcionadas são pares de estado global que repetem `state_accesses.json`, como na página |
| saída | o mesmo CSV, preenchendo julgamento (Sim/Não/Não sei) e justificativa |
| ordem | as linhas de cada sistema são embaralhadas de novo a cada execução, antes de formar os lotes; a semente fica registrada |
| lotes | 10 linhas por chamada |
| repetição | 3 execuções, em sessões separadas e independentes; vale a maioria por linha |
| modelos | três juízes, pagos primeiro (abaixo), cada um com a versão registrada |

## Modelos

**Prioridade aos pagos.** Os pagos costumam ser os modelos de topo de cada família e têm versão e provedor estáveis; os gratuitos mudam de cota e de disponibilidade. Aqui dá para priorizá-los porque cada chamada só lê texto (~0,8 M tokens de entrada por execução), ao contrário do agent-judge, em que cada sessão abre dezenas de arquivos e uma execução gastou de 2,7 a 8,4 M (3 a 10 vezes mais): lá só coube um pago por vez.

| ordem | modelo | contexto | raciocínio | custo de 1 execução | por quê |
|---|---|---|---|---|---|
| 1 | `openai/gpt-6-luna` | 1,05 M | sim | ~US$ 0,15 | da linhagem GPT usada nos estudos de LLM-as-a-judge; o mais barato da OpenAI; contexto de sobra para o maior prompt |
| 2 | `deepseek/deepseek-v4-pro` | 1 M | sim | ~US$ 1,00 | o juiz mais rigoroso no agent-judge (conferiu cada linha citada); repeti-lo dá coerência entre as duas avaliações. **Descartado** depois de rodar (ver Execução) |
| 3 | `google/gemini-3.8-flash` | 1 M | sim | ~US$ 1,10 | terceira família (Google), o Flash mais recente; vai por último porque o saldo (US$ 2,03) pode não bastar. **Não rodou:** o saldo não bastou (ver Execução) |
| 3′ | `qwen/qwen3.7-plus` | 1 M | sim | ~US$ 0,40 | só se, depois dos dois primeiros, o saldo for menor que US$ 1,30: outra família (Alibaba), cabe no que sobrar |
| 4 | `nvidia/nemotron-3-ultra-550b-a55b:free` | 1 M | sim | grátis | o mesmo do agent-judge; passou no piloto do nabstore |

Critérios comuns: **raciocínio** (julgar pela definição pede pensar sobre domínio e acoplamento, não só casar palavras); **contexto** de pelo menos 128 mil tokens, para caber o maior prompt (~90 mil, no udistrital) sem recorte; **família diferente** do Claude e entre si; e **custo** dentro do saldo. Os gratuitos vão por último e com até 3 execuções, porque as 72 chamadas cabem no limite diário (1.000 pedidos).

**Execuções dos pagos.** Com o saldo inicial, só coube uma execução por pago: três juízes de famílias diferentes valiam mais que três execuções de um só. Com o crédito extra, os pagos já rodados ganharam a 2ª e a 3ª execução (ver Execução), sem acrescentar modelos.

Estimativa por execução: ~0,79 M tokens de entrada (24 chamadas) e ~5,4 mil de saída por chamada, medidos no piloto do nabstore com o GPT-5.

Considerados e não usados:

| modelo | por quê não |
|---|---|
| `openai/gpt-5` | o plano inicial (passou no piloto); ~US$ 2,30 por execução sem a fila de lotes, que o OpenRouter não oferece para os modelos da OpenAI; não coube no orçamento |
| `google/gemma-4-31b-it:free` | escolhido de início; decidimos não acrescentar modelos além dos já rodados e usar o crédito extra nas execuções 2 e 3 dos pagos (o Gemma também estava com limite de taxa no Google) |
| `thinkingmachines/inkling:free` | escolhido de início; a versão gratuita só atende aplicativos de agente cadastrados no OpenRouter (erro 403 "only available on agentic harnesses"); um script de pesquisa não é um deles. As chamadas recusadas não foram guardadas |
| `google/gemini-2.5-pro`, `gemini-3.1-pro-preview` | mesmo preço do GPT-5 ou mais |
| `google/gemini-3.8-flash` | ~US$ 1,10 por execução; o saldo não bastou e entrou o Qwen |
| `deepseek/deepseek-v4-pro` | rodou, mas foi descartado: não fechou as 3 execuções (ver Execução) |
| Claude (Opus, Sonnet, Haiku) | mesma família de quem ajudou a construir o DAMFE: o juiz poderia favorecê-lo |

## Execução

| modelo | execução 1 | execução 2 | execução 3 | custo total |
|---|---|---|---|---|
| `openai/gpt-6-luna` | 166 de 166 linhas | 166 | 166 | US$ 0,32 |
| ~~`deepseek/deepseek-v4-pro`~~ (descartado) | 166 | 32 (parcial) | 27 (parcial) | US$ 1,49 |
| `qwen/qwen3.7-plus` | 166 | 166 | 166 | US$ 0,79 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 166 | 166 | 166 | grátis |

- **Ordem do crédito extra:** primeiro as execuções 2 e 3 do agent-as-a-judge (mais caras e mais importantes para a precisão da extração); o que sobrou foi para as execuções 2 e 3 dos pagos daqui, sem acrescentar modelos.
- **DeepSeek parado nas execuções 2 e 3:** nos lotes do udistrital ele alterava as colunas fixas ao copiar as linhas (ex.: a célula com a lista de vários micro frontends, ou nomes como `micro-frontends-profle-app`), em 6 de 7 lotes e nas 3 tentativas de cada; também com o provedor fixo (Baidu), então não é do provedor. Para não gastar o saldo em respostas inválidas, foi interrompido, e o resto foi para o Qwen. **Descartado da análise:** sem as 3 execuções no udistrital (139 das 166 linhas), não há maioria por linha nesse sistema, e misturar 1 e 3 execuções deixaria o juiz desigual aos outros. Refazer custaria ~US$ 1,50 com o mesmo erro provável. As respostas dele foram apagadas.
- **DeepSeek em vários provedores (execução 1):** 9 provedores escolhidos pelo OpenRouter (StreamLake 7, GMICloud 5, DigitalOcean 4, outros 8); cada um pode usar outra quantização; o provedor de cada chamada está no registro.
- **Gemini 3.8 Flash ficou de fora:** depois do DeepSeek sobraram US$ 0,87, abaixo dos US$ 1,30 da regra; entrou o Qwen.
- **Realinhamento:** o Qwen pôs a coluna vazia extra em 6, 9 e 13 lotes (execuções 1, 2 e 3); o luna em 1 e 4. Todos aceitos pela regra de Parâmetros, sem nova chamada.

## Parâmetros

Chamados pelo **OpenRouter** (API no formato da OpenAI), com `run_judge.py`.

| parâmetro | valor | por quê |
|---|---|---|
| `reasoning.effort` | `high`, em todos | julgar pela definição pede pensar; o mesmo nível em todos os modelos deixa a comparação justa. O OpenRouter traduz para o orçamento de raciocínio de cada modelo |
| `max_tokens` | 16.000 | cabe o raciocínio e o lote de 10 linhas com justificativas (o piloto usou ~5,4 mil) |
| temperatura, `top_p`, `top_k` | não enviados: vale o padrão de cada modelo (tabela abaixo) | os modelos da OpenAI com raciocínio não aceitam temperatura; para os outros, o padrão é o recomendado pelo fabricante. Acima de 0, as 3 execuções medem a estabilidade |
| `seed` | não usado | os modelos não garantem reprodução por semente; a reprodutibilidade vem do registro |
| provedor | só o GPT-5 é fixado (OpenAI, sem alternativa); nos outros, o OpenRouter escolhe e a resposta diz qual foi, e fica no registro | fixar todos arriscaria travar na fila de um provedor só; registrar deixa a variação visível |
| tentativas | até 2 novas, por resposta inválida ou erro de rede, com espera de 10 e 20 s | resposta com linha faltando ou alterada é refeita, não consertada à mão |
| `timeout` | 600 s por chamada | cabe o raciocínio longo do maior prompt |
| rede | só IPv4 | o IPv6 da rede quebrou durante a rodada do agent-judge |
| saída | CSV, conferido contra a entrada | o `#` e as colunas fixas de cada linha têm que voltar iguais |
| realinhamento | se a coluna do julgamento vem vazia e a seguinte traz Sim/Não/Não sei, a coluna vazia é removida; vale para todos os modelos, e o número de linhas realinhadas fica no registro (`realigned`) | é erro de contagem de vírgulas, não de julgamento: refazer a chamada repetia o erro, e descartar perderia julgamentos completos |

Padrões de amostragem de cada modelo, como o OpenRouter informa:

| modelo | temperatura | `top_p` | `top_k` |
|---|---|---|---|
| `openai/gpt-6-luna`, `openai/gpt-5` | não aceita (fixa pela OpenAI) | — | — |
| `deepseek/deepseek-v4-pro` | 1 | 1 | — |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1 | 0,95 | — |
| `qwen/qwen3.7-plus` | a do provedor (não informada) | — | — |

Cada chamada é uma requisição nova, sem histórico: as 3 execuções são independentes por construção.

## Prompts

`build_prompts.py` gera, a partir deste template, dos artefatos (em `sistemas/<sistema>/artefatos/`) e dos CSVs, um prompt completo por sistema, execução e lote em `sistemas/<sistema>/execucao-<n>-lote-<k>.md` (72 ao todo; o maior tem ~90 mil tokens, no udistrital). Cada arquivo tem `# SYSTEM` e `# USER`. O `sistemas/manifest.csv` diz as linhas e a semente de cada um.

## Registro

Para cada chamada, um registro em `runs/<modelo>/<sistema>/execucao-<n>-lote-<k>.json`:

- modelo e provedor **devolvidos** pelo OpenRouter (a versão que de fato respondeu), id da geração, data e hora, tokens e custo
- os parâmetros enviados
- hash do `template.md` usado e a semente do embaralhamento
- entrada e saída completas (o raciocínio também, se o provedor devolver)

As respostas, montadas na ordem original, ficam em `respostas/<modelo>/execucao-<n>/avaliacao-<sistema>.csv` — o mesmo formato dos coautores. O resumo dos julgamentos sai de `resultados.py` em [`resultados.md`](resultados.md).

## O que faltou (15/10/2026)

Mede a revocação das regras, dada a reconstrução: por sistema, o juiz recebe a reconstrução corrigida ([`../reconstrucao-corrigida/`](../reconstrucao-corrigida/), a mesma da parte 2 do agent-judge) e as detecções do DAMFE, e aponta as ocorrências dos 7 anti-padrões que não estão na lista. A revocação da reconstrução fica com o agent-judge. Prompt em [`template-faltou.md`](template-faltou.md), com as definições literais de `template.md`; roda com [`faltou.py`](faltou.py), uma chamada por sistema e execução, 3 execuções; registro em `runs-faltou/`.

- **Formato dos artefatos:** o mesmo em todos os sistemas, com chamadas de API agrupadas por endpoint e acessos a estado por chave, para o udistrital (8 MB de JSON) caber no contexto sem perder o que os anti-padrões usam.
- **Contagem:** uma ocorrência vale quando aparece em 2 das 3 execuções; toda ocorrência é conferida por nós antes de virar falso negativo.
- **Modelos:** os mesmos juízes das detecções. Primeiro o gratuito, `nvidia/nemotron-3-ultra-550b-a55b:free`; com crédito, luna e Qwen, com o mesmo prompt (decisão de 15/10: ver se o resultado vale antes de gastar). Outros gratuitos testados e descartados (registros em `descartados/faltou-*`): `thinkingmachines/inkling:free` só funciona em agentes de código cadastrados (403); `google/gemma-4-31b-it:free` só devolveu limite de taxa; `dots-studio/dots-3-note-preview:free` completou as 30 chamadas, mas fica fora para os juízes serem os mesmos das detecções.
- **Cobertura:** as 30 chamadas dos três juízes completaram. Custo: US$ 0,03 (luna) e US$ 0,20 (Qwen). Resultado em [`resultados.md`](resultados.md), seção "O que faltou".

## Ameaças à validade mitigadas

| tipo | ameaça | mitigação |
|---|---|---|
| construto | **o juiz usar uma ideia própria do anti-padrão**, diferente da dos coautores | definição oficial do catálogo, literal e com a fonte — a mesma base para o LLM e para os coautores |
| construto | **o juiz aprender a heurística do DAMFE** e só conferir a conta | exemplos tirados do catálogo, sem limiar nem contagem; instrução de julgar pela definição |
| interna | **viés de concordância** (tendência a dizer "Sim", já que toda linha é uma detecção) | exemplos balanceados: um "sim" e um "não" para cada um dos 7 anti-padrões; instrução de que ocorrência é problema com as consequências da definição |
| interna | **não determinismo do LLM** (respostas diferentes a cada chamada) | 3 execuções em sessões independentes, com a maioria por linha; temperatura e raciocínio fixos |
| interna | **vazamento das respostas** pelos exemplos | nenhum exemplo vem dos 12 sistemas avaliados |
| interna | **alucinação**, ou julgar pelo que lembra dos 12 sistemas (públicos, podem estar no treino) | "use só os fatos fornecidos; se não bastam, Não sei" |
| interna | **viés de posição** (a ordem das linhas influenciar o julgamento) | ordem embaralhada a cada execução, e os lotes mudam junto |
| interna | **perda ou alteração de linhas** em entradas longas | lotes de 10; o `#` é preservado e a saída é conferida linha a linha |
| conclusão | **anti-padrão sem exemplo** ser julgado com menos critério | os 7 têm exemplo, inclusive Cyclic e Hub-like |
| confiabilidade | **resultado não reproduzível** | registro de cada chamada: modelo, versão, data, parâmetros, entrada e saída |
| independência | **o juiz ser da mesma família de quem ajudou a construir o DAMFE** (Claude) | nenhum juiz é Claude |
| conclusão | **o resultado depender de um modelo só** | três juízes de famílias diferentes (OpenAI, Alibaba, NVIDIA) |
