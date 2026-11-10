# Correções da reconstrução

A reconstrução é avaliada e corrigida antes da avaliação das detecções, para que um erro de extração não vire erro de detecção em cascata. Os defeitos vêm do agent-judge ([`achados.md`](llms/agent-judge/achados.md)); cada correção é genérica (pela API documentada da tecnologia ou pela semântica de JS/TS) e tem um teste em `damfe/tests/` que falha no código antigo.

Versão avaliada: DAMFE `c8f439a` (12/10/2026).

## Decisões (14/10/2026)

| pergunta | decisão |
|---|---|
| `removeItem` conta como gravar estado? | **sim**: a API de Storage trata `setItem`, `removeItem` e `clear` como escritas |
| o local de uma tela ou fragmento aponta para onde? | **a definição do componente** (arquivo e linha do componente) |
| o micro frontend é identificado por quê? | **pelo diretório / repositório** |
| componente raiz que só monta providers e o router é tela? | **não**: só é tela o que uma rota renderiza |

## Defeitos e correções

| # | tipo | sistema | defeito | correção | teste | estado |
|---|---|---|---|---|---|---|
| 1 | navegação | udistrital | chamada HTTP lida como navegação, porque o caminho da API coincide com a rota de outro MFE (`plan-accion.component.ts:107`) | o argumento de uma chamada que o extrator de chamadas HTTP reconhece como requisição (cliente conhecido, `HttpClient` injetado ou função que repassa a URL a um deles) não é candidato a navegação. As requisições ficam memorizadas no contexto da varredura, para a extração não rodar duas vezes (`api_calls.extracted`) | `test_http_request_to_a_path_that_is_another_route_is_not_navigation` | feito |
| 2 | navegação | fubaritico | rota do servidor Express (`app.get('/')`) lida como navegação (`apps/photos/server.js:24`) | módulo que importa um módulo nativo só do Node (`fs`, `path`, `http`, `node:*`... de `module.builtinModules`, menos os que têm pacote de mesmo nome para o navegador, como `events` e `buffer`) roda no servidor: não gera navegação. O webpack 5 e o Vite não levam esses módulos ao navegador | `test_server_module_routes_are_not_navigation` | feito |
| 3 | navegação | fubaritico | `useMatch` (teste da rota atual) lido como ida para a rota (`HeaderSearch.tsx:20`) | o argumento das funções que comparam um padrão com a URL atual não é destino: `useMatch`, `matchPath`, `matchRoutes`, `useRouteMatch` (React Router) e `pathToActiveWhen` (single-spa), pelo import | `test_route_matchers_are_not_navigation` | feito |
| 4 | fragmento, composição | LBHackney-IT | qualquer export vira fragmento, até objeto de configuração (`export { locale, processes }`) | o nome exportado é seguido pelos `export ... from` e `import` do projeto até a declaração (`exported_values.py`); se for dado (texto, número, lista, objeto que não é componente Vue, `type`, `interface`, `enum`), não é fragmento. O que não dá para seguir (pacote, chamada como `memo()`) continua fragmento | `test_exported_data_is_not_a_fragment` | feito |
| 5 | tela | pagopa | `Redirect` do react-router lido como tela, num arquivo de mock | a rota cujo componente é `<Redirect>` (React Router v5) ou `<Navigate>` (v6) só redireciona: não vira tela, no JSX e no objeto de rotas | `test_redirect_route_is_not_a_screen` | feito |
| 6 | tela | udistrital | rota sem o prefixo do módulo carregado sob demanda (`/aspirantes` em vez de `/inscripciones/aspirantes`) | as rotas de um arquivo carregado por `loadChildren` (função `import()` ou a forma antiga `'./x.module#X'`) respondem abaixo da rota que o carrega; se o carregado é um `NgModule` sem rotas, o prefixo passa aos arquivos de rotas que ele importa (`forChild`). Carregamentos encadeados somam os prefixos | `test_lazy_loaded_angular_routes_keep_the_parent_path` | feito |
| 7 | tela, fragmento | vários | o local junta o arquivo do componente com a linha da rota ou do export | o local de tela e fragmento é a definição do componente: arquivo do componente e linha da declaração, ou do `export default` quando o import padrão lhe dá outro nome (`declarations.py`). O fragmento reexportado (`export { X } from "./x"`), que ficava sem arquivo, passa a ter o do componente | `test_screen_and_fragment_point_to_the_component_definition` | feito |
| 8 | acesso a estado | Grupo-10 | `removeItem` (decisão acima) | nenhuma: o DAMFE já tratava `removeItem` como escrita (`libraries.STORAGE_WRITE`); a decisão confirma o comportamento, e os `parcial` do agent-judge nesses itens eram do juiz | — | sem mudança |
| 9 | micro frontend | udistrital | MFE pelo nome registrado em vez do diretório (`mf-tipo-inscripcion`) (decisão acima) | o identificador de cada micro frontend passa a ser o último segmento do seu diretório (o caminho inteiro, se dois terminam igual), em todas as referências; o nome registrado fica em `metadata.registered_name` (`domain/naming.py`, aplicado na montagem da arquitetura). Os testes antigos passaram a esperar o nome do diretório | `test_microfrontend_is_named_after_its_directory` | feito |
| 10 | tela | topcoder | `root.component.js` que só monta providers vira tela (decisão acima) | sem roteador interno, a tela é o primeiro componente com conteúdo próprio: desce do raiz enquanto ele só renderiza componentes de pacote (providers) e um único componente do projeto, sem HTML próprio | `test_root_that_only_wraps_providers_is_not_the_screen` | feito |
| 11 | micro frontend | LBHackney-IT | o molde do gerador de projetos (`mtfh-frontend/packages/generator/.../templates`, com `"name": "<%= name %>"`) virou micro frontend: o código `c8f439a` já o achava, embora as saídas avaliadas (de 10/10) não | pacote cujo `package.json` existe mas não é JSON não é unidade: o npm não o instala | `test_generator_template_is_not_a_microfrontend` | feito |

Ajustes durante a validação nos sistemas: na correção 4, o objeto só é componente Vue com `render`, `template` ou `setup` (o `locale` do LBHackney tem uma chave `components`), e `export * as ns from` é dado (objeto de namespace do módulo); na correção 7, o local segue também os barris (`views/index.ts`) até o arquivo do componente.

**Limitação que fica:** no udistrital, `documentos.service.ts:13` continua como navegação. O cliente vem de `this.request.client('X')`, um método que devolve um objeto com `get`, e o campo é tipado como `ReturnType<RequestManager['client']>`; seguir isso exige inferir o tipo do retorno, o que o DAMFE não faz.

Fora da reconstrução: no **Bahmni**, o host que compõe os fragmentos (`openmrs-module-bahmniapps`) não está no recorte do sistema; é questão de seleção dos repositórios, não defeito do DAMFE.

## Resultado nos sistemas (14/10/2026)

O DAMFE corrigido rodou de novo nos 12 sistemas (111 testes passando). Comparado às saídas avaliadas:

| sistema | o que mudou na reconstrução |
|---|---|
| udistrital | navegações 17 → 9 (as 8 que saíram eram chamadas HTTP); telas 251 → 255 (rotas sob `loadChildren` com o prefixo certo) |
| fubaritico | navegações 3 → 0 (2 do servidor Express, 1 `useMatch`) |
| LBHackney-IT | fragmentos 3 → 1 e composições 3 → 0 (`locale` e `processes` eram dados) |
| pagopa | telas 15 → 12 (os 3 `<Redirect>`) |
| todos | nome de cada micro frontend pelo diretório; local de telas e fragmentos na definição do componente |

**As detecções não mudaram** em nenhum sistema: mesmos anti-padrões, mesmos micro frontends (mapeados pelo nome registrado) e mesmas rotas. Os erros corrigidos não chegavam às regras; a correção evita que cheguem.

Saídas novas em `damfe/` (páginas) e `damfe/artefatos/` (JSON); a planilha `profissionais/avaliacao.xlsx` foi regerada delas, com as mesmas 43 linhas e os nomes novos. As cópias em `llms/*/sistemas/` ficam como estavam: são o que os juízes avaliaram.

As saídas avaliadas são de 10/10 (manifest `generated_at`), de uma árvore anterior ao commit `c8f439a` de 12/10.

## Link para o catálogo (14/10/2026)

Cada detecção passou a levar o link da definição do anti-padrão no catálogo (`reference` em `detections.json`, de `AntiPattern.reference` de cada regra), mostrado como "Referência" ("Catalog of Micro Frontends Anti-patterns ↗") no detalhe da linha na página. Na planilha, o nome do anti-padrão é o link. As detecções não mudaram; páginas, artefatos e planilha foram regerados. Teste: `test_each_detection_links_to_its_definition_in_the_catalog`.

## O que faltou (15/10/2026; correções em 16/10/2026)

A parte 2 do agent-judge mediu o que a reconstrução corrigida (`f88ae29`) deixa de extrair: 63 falsos negativos em 20 MFEs sorteados (10 sistemas, mais 10 do udistrital), conferidos no código ([`resultados.md`](llms/agent-judge/resultados.md), "O que faltou"). Cada defeito foi classificado por quanto a correção serve a um DAMFE genérico; as que valem a pena foram aplicadas sobre `1280bc9`, cada uma com um teste em `tests/test_missing_review.py` que falha no código anterior.

| # | tipo | sistema | defeito | correção | estado |
|---|---|---|---|---|---|
| 26 | micro frontend | udistrital | os 7 shells saem com o mesmo id (`plantillas_root_mf`) e as relações se misturam | unidades registradas com o mesmo nome recebem o nome do diretório antes de qualquer relação ser extraída (`naming.distinct`) | feito |
| 12 | API, estado | LBHackney, fubaritico, Insta-Graph | código de pacote compartilhado importado pelo MFE não é seguido | import de pacote do corpus (workspace ou repositório irmão, pelo `name` do `package.json`) resolve para o arquivo de entrada dele; o código do pacote que não é unidade conta para cada MFE que o importa (`singlespa/shared.py`), e o índice de símbolos segue os reexports (`export * from`) | feito; não cobre SWR (LBHackney) nem o cliente gerado do hey-api (fubaritico) |
| 17 | API | udistrital | URL com ternário na função que embrulha o cliente | vale o que as duas formas do ternário têm em comum, se terminar na URL recebida | feito |
| 14 | estado | topcoder | chave de storage com trecho de runtime é descartada | o trecho vira `{param}`; sem nenhum texto conhecido, não há chave. Inverte a decisão anterior ("chave de runtime não é fatia"); os dois testes antigos passaram a esperar `cart_{param}` | feito |
| 15 | navegação | LBHackney, pagopa | dono do destino só pelo `activeWhen` | sem `activeWhen` que case, o dono é a única unidade com tela naquele caminho | feito; no pagopa as rotas do destino (`ENV.ROUTES`) continuam sem resolver |
| 16 | API | Bahmni | URL montada com `new URL(...)` | `new URL(caminho, base)`, `toString()` e `href` avaliados | feito |
| 18 | navegação | fubaritico | template string cortada no prefixo | o destino guarda o padrão inteiro (`/movie/{param}`), que casa com a rota dinâmica | feito |
| 27 | API | udistrital | URL continua depois do endpoint na função que embrulha o cliente | o que segue a URL recebida vira sufixo, com `{param}` no que é de runtime | feito |
| 21 | estado | Grupo-10 | `localStorage.clear()` | gravação sem chave (`*`) | feito |
| 24 | estado | pagopa | `useSelector` com outro nome | `const useAppSelector = useSelector` e `useSelector.withTypes()` contam como seletor | feito; no pagopa o MFE continua com store privado (`configureStore` próprio) |

No limite, não aplicadas: **#13** (tabela de rotas própria montada em laço, pagopa, 9), **#28** (URL em campo da classe, `this.environment.X`, udistrital, 2), **#20** (destino de item de lista em `.map`, 2).

Não valem a pena: **#25** (cliente GraphQL Apollo, 1), **#19** (evento em script inline do `index.ejs`, 3), **#23** (`document.cookie`, 2), **#22** (propriedade global de `window`, 2).

Limitações (fato fora do código-fonte): cliente gerado da spec OpenAPI no build (pagopa, 18) e URL inteira do `environment.json` (gematik, 3).

### Resultado nos sistemas (16/10/2026)

Os 12 sistemas rodados de novo; artefatos e páginas em `avaliacao/damfe/` substituídos (cópia anterior fora do repositório). A planilha dos profissionais (`profissionais/avaliacao.xlsx`) **não** foi regerada.

| sistema | o que mudou |
|---|---|
| udistrital | chamadas de API 1.972 → 2.252 (235 PUT e 45 DELETE das embrulhadoras com ternário e sufixo); os 7 shells com id próprio; Hammering 116 → 121 |
| LBHackney-IT | navegações 0 → 9; chamadas 0 → 5 e acessos a estado 1 → 51, do `@mtfh/common`; detecções novas: Global State (`features`, nos 5 MFEs) e Hammering (`/oauth2/token`, nos 5) |
| fubaritico | navegações 0 → 5 (destinos em template string) |
| topcoder-archive | acessos a estado 3 → 10 (chaves com `{param}`) |
| Bahmni | chamadas de API 9 → 11 (`new URL`) |
| Grupo-10-Pos-FIAP | acessos a estado 24 → 25 (`clear()`) |
| nabstore | acessos a estado 17 → 18 |
| demais | sem mudança |
