<!-- início do trecho gerado por resultados.py -->
# LLM as a judge — resultados

Gerado por `resultados.py` a partir de `respostas/`. Sem nabstore e halloween (160 detecções). Veredito da linha: maioria das 3 execuções; no empate, o mais severo (Não, Não sei, Sim). "Sim" quer dizer que o juiz concorda com a detecção do DAMFE.

## Por juiz

| juiz | Sim | Não | Não sei | unânimes nas 3 execuções | κ de Cohen entre as 3 |
|---|---|---|---|---|---|
| openai-gpt-6-luna | 80% | 18 | 14 | 145 de 160 (91%) | 0.82 |
| qwen-qwen3.7-plus | 86% | 22 | 0 | 132 de 160 (82%) | 0.60 |
| nvidia-nemotron-3-ultra-550b-a55b-free | 84% | 10 | 16 | 139 de 160 (87%) | 0.66 |

## Concordância com o DAMFE, por anti-padrão

Das detecções de cada anti-padrão, a parte em que o juiz respondeu Sim (concorda que é o anti-padrão), pelo veredito da linha. Ex.: das 35 de nano-frontend, a luna concordou com 4 (11%). Com 1 ou 2 detecções, o percentual não permite concluir nada.

| anti-padrão | detecções | openai-gpt-6-luna | qwen-qwen3.7-plus | nvidia-nemotron-3-ultra-550b-a55b-free |
|---|---|---|---|---|
| global-state-communication | 2 | 2 (100%) | 2 (100%) | 2 (100%) |
| hammering-apis | 120 | 120 (100%) | 117 (98%) | 120 (100%) |
| mega-frontend | 2 | 2 (100%) | 2 (100%) | 2 (100%) |
| nano-frontend | 35 | 4 (11%) | 17 (49%) | 10 (29%) |
| one-for-all | 1 | 0 (0%) | 0 (0%) | 0 (0%) |

## Entre os juízes

| par | mesmo veredito | κ de Cohen |
|---|---|---|
| openai-gpt-6-luna × qwen-qwen3.7-plus | 141 de 160 (88%) | 0.60 |
| openai-gpt-6-luna × nvidia-nemotron-3-ultra-550b-a55b-free | 134 de 160 (84%) | 0.48 |
| qwen-qwen3.7-plus × nvidia-nemotron-3-ultra-550b-a55b-free | 140 de 160 (88%) | 0.54 |

<!-- fim do trecho gerado -->

## Análise das discordâncias

Lidas as justificativas de todo "Não" e "Não sei" dos 3 juízes nas 3 execuções (160 detecções, sem nabstore e halloween). Números nas tabelas acima.

### Nano Frontend

35 detecções. Os juízes aceitam pouco: 4 (luna), 17 (Qwen) e 10 (Nemotron), pela maioria das execuções. Só 2 têm Sim dos três (`navigation-drawer` do Grupo-10 e `comp-library` do diego-coronado); 5 têm Não dos três (`auth`, `appointments`, `patient-records`, `profile-app` do topcoder e `usuario_rol_mf`); as outras 28 dividem os juízes.

**O tamanho decide.** Toda detecção de nano saiu do piso absoluto do DAMFE (telas + fragmentos ≤ 5, com código abaixo da mediana do sistema). Os juízes só aceitam, e nem sempre, quando o micro frontend tem **uma** tela ou fragmento:

| telas + fragmentos | detecções | aceitas (2 ou 3 juízes dizem Sim) | rejeitadas (nenhum juiz diz Sim) |
|---|---|---|---|
| 1 | 16 | 10 | 3 |
| 2 | 7 | 1 | 5 |
| 3 | 5 | 0 | 4 |
| 4 | 6 | 1 | 5 |
| 5 | 1 | 0 | 1 |

O que falta para fechar a linha são as divididas (só 1 juiz diz Sim).

**Por que discordam** (226 justificativas de Não e Não sei; uma pode ter mais de um motivo):

| motivo | justificativas | quem mais usa |
|---|---|---|
| o micro frontend cobre um domínio inteiro e coeso, não é um componente de UI | 172 | os três |
| os artefatos não bastam para saber se a decomposição é ineficaz | 100 | luna (66), Nemotron (33) |
| o código não é pequeno (arquivos, linhas) | 93 | Nemotron (47), Qwen (32) |
| a tela está marcada como não alcançável | 11 | luna |
| é transversal ou biblioteca (menu, layout) | 5 | os três |

Exemplos:
- *"Representa um domínio de negócio completo (agendamentos) com sua própria tela, não sendo uma mera componente de UI."* (Qwen, `appointments`)
- *"O MFE tem 5 telas, 60 arquivos e ~2150 linhas de código; tamanho não trivial e sem indícios de fragmentação ineficaz."* (Nemotron, `ejecucion_auditoria_mf`)
- *"O MFE tem uma única tela, mas isso não basta para concluir que representa uma decomposição fragmentada [...]; os fatos não esclarecem se perfil é um domínio coeso."* (luna, `mf-user`)

**O que isso diz:**
1. **O critério é outro.** O catálogo define o problema pelo tamanho ("only a few screens or fragments"), que é o que o DAMFE mede, e a consequência pela confusão com componente de UI. Os juízes julgam pela consequência: um micro frontend pequeno, mas de um domínio só, não é nano para eles. O exemplo "não" do prompt reforça isso ("é uma unidade alinhada a um domínio inteiro"), e os coautores recebem o mesmo catálogo.
2. **O piso de 5 é generoso.** Com 2 a 5 telas, quase nenhum juiz concorda. O piso não vem do catálogo.
3. **Falta informação de domínio.** Os artefatos dizem quantas telas e linhas, não o que o micro frontend faz; daí a maior parte dos "Não sei" da luna e do Nemotron.
4. **Cada juiz tem um perfil:** a luna prefere "Não sei" quando falta contexto; o Qwen nunca usa "Não sei" e decide pelo domínio; o Nemotron decide pelo código (arquivos e linhas).

**Como melhorar a detecção.** Somando a tabela acima até cada piso:

| piso (telas + fragmentos) | detecções | aceitas |
|---|---|---|
| ≤ 5 (atual) | 35 | 12 (34%) |
| ≤ 2 | 23 | 11 (48%) |
| = 1 | 16 | 10 (62%) |

Com 2 ou mais, só 2 de 19 são aceitas (`poliza_mf` e `photos`).

1. **Piso = 1.** Fica mais perto da consequência que o catálogo descreve, o micro frontend confundido com componente de UI: as duas aceitas pelos três são um menu (`navigation-drawer`) e uma biblioteca de componentes (`hs-comp-library`). O 5 foi escolha declarada, não medida (`nano_frontend.py`); o critério de outlier (Tukey) continua para os sistemas grandes.
2. **Fatos de domínio na detecção:** rotas das telas, nomes dos fragmentos e quantos endpoints o micro frontend chama. Ataca os 100 "os artefatos não bastam" sem mudar o que é detectado.
3. **Critério de código mais duro: não.** Os três rejeitam as `portal-*` do gematik (1 tela, mais de 2 mil linhas), mas as linhas não separam aceitas de rejeitadas (`auditoria-mf`, 1570 linhas, aceita; `auth`, 995, rejeitada).

Cuidado: escolher o piso por estes veredictos é ajustar a regra ao próprio conjunto de avaliação, e com juízes LLM. Proposta: manter o piso na avaliação dos coautores, reportar a precisão por piso (juízes e coautores) e propor o piso 1 como resultado, não como premissa. A proposta 2 pode entrar já, porque só melhora a evidência.

### One Micro Frontend for All

1 detecção (Grupo-10), rejeitada pelos 3 juízes nas 3 execuções, sempre pelo mesmo motivo: *"Não há um MFE importado por todos os outros; compositions.json está vazio"*. O catálogo define o anti-padrão pela **importação** ("imported by all other MFEs"); a regra do DAMFE conta **qualquer conexão** (navegação, comunicação, composição), sem direção. É divergência de construto, não de julgamento.

### Hammering APIs

Aceito quase sempre (117 a 120 de 120). A exceção é o Qwen em duas execuções, no topcoder (3 rotas) e no Grupo-10 (1): *"Os MFEs são montados em rotas distintas, sem sobreposição de ativação; não há chamadas duplicadas na mesma sessão"*. Ele exige que as chamadas sejam simultâneas, o que o catálogo não pede ("independently call the same API endpoint").

## O que faltou nas detecções

Os juízes recebem a reconstrução corrigida e as detecções do DAMFE e apontam o que deveria ter sido detectado (`faltou.py`, `template-faltou.md`). Uma omissão conta quando aparece em 2 das 3 execuções do juiz. Conferimos cada uma nos artefatos e no código.

| omissão | juízes (de 3) | conferência |
|---|---|---|
| nano: `billing`, `laboratory`, `pharmacy` (diego-coronado) | 3 | **falso negativo.** 1 tela e 1 fragmento, como `appointments` e `patient-records`, que foram detectados. Ficam de fora só pelo código: 656 a 669 linhas, com mediana de 656 e a comparação estrita (<) |
| nano: `micro-frontend-feed` (Insta-Graph) | 2 | **falso negativo**, pelo mesmo motivo: 1 tela, 132 linhas contra a mediana de 126,5. `micro-frontend-user` (121) foi detectado |
| cyclic: `planeacion_pendientes` ↔ `planeacion_seguimiento` (udistrital), por navegação | 3 | decisão de projeto: a regra não conta navegação ("ida e volta entre telas é fluxo do produto") |
| cyclic por comunicação entre MFEs montados lado a lado (udistrital: `core_mf_cliente` ↔ `inscripcion`, `plantillas_root` ↔ `auditoria`) | 1 | decisão de projeto: a regra só conta ciclo dentro de uma tela |
| cyclic pelo `localStorage:token` (Grupo-10) | 1 | já detectado como global-state |
| mega: `DEMIS-portal-disease` (gematik, 97 mil linhas, 19× a mediana), `gigs-app` (topcoder), `statement` (Grupo-10), `ipd-frontend` (Bahmni) | 1 a 2 | decisão de projeto: o mega se abstém com menos de 8 MFEs (`MIN_SAMPLE`), e os 4 sistemas têm de 2 a 5 |
| mega: `sga_cliente_inscripcion` (udistrital, 27 mil linhas e 6 telas), `gestion_contractual` | 1 | decisão de projeto: exige telas **e** linhas acima da cerca, e as telas não passam |
| hub: `host` (fubaritico), `home` (diego-coronado) | 1 | erro do juiz: cada fragmento é montado em uma rota própria (`router.tsx`), não numa tela só |

**O que isso diz:**
- O único falso negativo de implementação é o critério da mediana no nano. Em sistema pequeno e homogêneo, metade dos MFEs fica na mediana ou acima dela por construção, e unidades iguais recebem vereditos diferentes. Proposta: comparar com uma folga, ou só exigir o código quando houver distribuição para medir (como já faz o Tukey).
- **Contagem dupla no nano** (conferido em 15/10): no diego-coronado, a tela e o fragmento de cada MFE são o mesmo componente (`billing/vite.config.ts:16` expõe `./Billing`, e o host monta `<Route path="/billing">` com ele em `home/src/main.tsx:44`). A reconstrução está certa; a regra é que soma os dois (`nano_frontend.py:65`). Só acontece nesses 5 MFEs, e só pesa se o piso cair para 1.
- O resto são decisões de projeto que os juízes não seguem: ciclo por navegação, e o mega em sistema pequeno. O mega tem o mesmo problema que o nano já resolveu com o piso absoluto: o `DEMIS-portal-disease` é a maior unidade do conjunto e não é avaliado.

## O que faltou na reconstrução

No [`agent-judge/resultados.md`](../agent-judge/resultados.md).

## Para decidir

- O piso do nano muda já (para 1) ou só depois dos coautores, como resultado (ver "Como melhorar a detecção")?
**Decidido (15/10): nenhuma regra muda antes das respostas dos coautores.** As propostas (piso, folga na mediana, contagem dupla, mega em sistema pequeno) ficam para depois, como resultado.

- O critério de código do nano ganha folga (ver "O que faltou")? E o mega ganha um critério para sistemas com menos de 8 MFEs?
- A regra do one-for-all segue o catálogo (só importação) ou fica como está e a divergência vai para as ameaças?
- O prompt dos juízes e o material dos coautores devem deixar explícito que o nano é medido por tamanho?
