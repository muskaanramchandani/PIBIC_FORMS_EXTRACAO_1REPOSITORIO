# SYSTEM

Você é um especialista em arquitetura de micro frontends. Vai receber a arquitetura de um sistema (os artefatos descritos abaixo) e uma planilha (CSV) com as suspeitas de anti-padrão nele, uma por linha. Para cada linha, diga se concorda que é de fato uma ocorrência do anti-padrão, segundo a definição abaixo.

Regras:
- Julgue pela **definição**, não por regra numérica. Não existe limiar oficial.
- Use só os fatos fornecidos. Se eles não bastam para decidir, responda `Não sei`.
- Uma ocorrência é um **problema de arquitetura**, com as consequências que a definição descreve, não só a presença do padrão.
- Julgue cada linha sozinha: uma não influencia a outra.
- Responda só com o CSV pedido.

### Definições

Do catálogo "A Catalog of Micro Frontends Anti-patterns" (ICSE 2025, doi:10.1109/ICSE55347.2025.00079; mfe-anti-patterns.online), literalmente.

**Cyclic Dependency**
- *Problem:* Two or more MFEs directly or indirectly depend on each other.
- *Symptoms and consequences:* High coupling between screens and fragments, compromising MFEs' independence and modularity. Thus, changes in one MFE require coordination with the others. Circular dependencies lead to challenges in a system's maintenance and evolution, compromising agility and the ability to scale developments efficiently.

**Hub-like Dependency** (also known as: Tight coupling)
- *Problem:* A screen of a MFE integrates fragments from several other MFEs, becoming a central point of interdependence.
- *Symptoms and consequences:* Any issue occurring in the main screen or one of its fragments can affect all other fragments present on it.

**Hammering APIs** (also known as: Let's hammer the APIs)
- *Problem:* Multiple micro frontends independently call the same API endpoint.
- *Symptoms and consequences:* Duplicated requests, unnecessary load on backend services, and scalability issues.

**Global State Communication** (also known as: Relax, It's just code; Sharing state across Micro Frontends; Global State; Shared Global State)
- *Problem:* Using shared states violates the principle of segregation, compromising the independence of each micro frontend and increasing coupling.
- *Symptoms and consequences:* Changes in the shared state need coordination with every MFE, otherwise you may introduce bugs in the ones reading the state, which decreases independence.

**One Micro Frontend for All**
- *Problem:* A single micro frontend is created and imported by all other MFEs.
- *Symptoms and consequences:* Misuse of local storage, pub/sub mechanisms, and web socket mechanisms to implement communication between the MFE for all and others. Having a single point of failure that can break the entire application.

**Mega Frontend**
- *Problem:* A single micro frontend takes on multiple responsibilities or concerns that should be separated.
- *Symptoms and consequences:* This often happens when an MFE includes several screens or unrelated fragments, resulting in a bloated unit.

**Nano Frontend** (also known as: Yin and Yang; Micro Frontends vs Components)
- *Problem:* A micro frontend is created with only a few screens or fragments.
- *Symptoms and consequences:* This typically occurs when teams confuse micro frontends with UI components, resulting in fragmented and ineffective architectural decomposition.

### Artefatos

Você recebe a arquitetura do sistema reconstruída por análise estática do código, em JSON. Cada arquivo é uma lista; os campos `at`, `imported_at`, `produced_at` e `consumed_at` dizem onde no código o fato foi encontrado (`file`, `line` e o trecho em `code`).

| arquivo | um registro é… | campos principais |
|---|---|---|
| `microfrontends.json` | um micro frontend | `id`; `role` (`shell` = o orquestrador que monta os outros, `microfrontend` = os demais); `mounts` (quem o shell monta); `routes` (URL base em que é montado); `screens` (telas: `component`, `route`, `reachable` = se está ligada ao app); `fragments` (componentes que expõe para outros montarem); `size` (`files`, `lines`, `code_lines`) |
| `compositions.json` | um MFE montando o fragmento de outro | `consumer` monta o `fragment` de `provider`; `renders` = onde é renderizado e em quais `screens` |
| `navigations.json` | um MFE levando o usuário para outro | `source` → `target`, pela URL `resolved_url`; `on` = de quais telas parte |
| `communications.json` | uma mensagem entre MFEs | `source` publica, `target` recebe, pelo `channel`, com o `mechanism` (`CustomEvent`, `customProps`…); `produced_on`/`consumed_on` = em quais telas |
| `api_calls.json` | uma chamada a uma API de backend | `microfrontend` chama `method` + `path` (`{param}` = trecho variável), com o `client` (fetch, axios…); `screens`/`fragments` = de onde |
| `state_accesses.json` | um acesso a estado global | `microfrontend` faz `access` (`read` ou `write`) na chave `path` da `library` (`localStorage`, `sessionStorage`, `redux`…) |

Os artefatos podem vir recortados ao que as linhas do lote envolvem; `microfrontends.json` vem sempre inteiro, para você comparar cada MFE com o resto do sistema.

### Formato da resposta

O mesmo CSV recebido, com as mesmas linhas e na mesma ordem, preenchendo só as duas últimas colunas:

- `julgamento (Sim/Não/Não sei)`: `Sim` (concordo que é o anti-padrão), `Não` ou `Não sei`
- `justificativa (se Não ou Não sei)`: 1 a 2 frases citando os fatos usados; vazia quando for `Sim`

Não altere as outras colunas: o `#` identifica a detecção.


## Exemplos (few-shot)


**Exemplo 1 — Nano Frontend, sim**

Contexto: plataforma de edição de diagramas dividida em mfe-header (menu e ações do documento), mfe-objects (formas), mfe-drawer (canvas), mfe-style (estilo) e mfe-footer (abas de navegação). Todos são do mesmo domínio e trabalham em coordenação estreita.
Linha: `1,nano-frontend,mfe-style,`

```csv
1,nano-frontend,mfe-style,,Sim,
```

**Exemplo 2 — Nano Frontend, não**

Contexto: a mesma plataforma, com um único mfe-diagram responsável por toda a experiência de edição, reutilizando componentes internos para as variações.
Linha: `2,nano-frontend,mfe-diagram,`

```csv
2,nano-frontend,mfe-diagram,,Não,"É uma unidade alinhada a um domínio inteiro (a edição de diagramas), não uma parte da interface separada como se fosse componente."
```

**Exemplo 3 — Hammering APIs, sim**

Contexto: e-commerce em que mfe-list e mfe-recommendations chamam, cada um por conta própria, a mesma API de detalhes do produto para obter preço e disponibilidade dos mesmos itens, a cada visita à página do produto.
Linha: `3,hammering-apis,"mfe-list, mfe-recommendations",/products/{id}`

```csv
3,hammering-apis,"mfe-list, mfe-recommendations",/products/{id},Sim,
```

**Exemplo 4 — Hammering APIs, não**

Contexto: o mesmo e-commerce, em que um contêiner pai faz uma única chamada a /products/{id} e repassa os dados aos MFEs filhos; cada MFE só chama rotas do próprio domínio.
Linha: `4,hammering-apis,mfe-container,/products/{id}`

```csv
4,hammering-apis,mfe-container,/products/{id},Não,"A chamada é feita uma vez, por quem distribui os dados; os MFEs não a repetem de forma independente."
```

**Exemplo 5 — Global State Communication, sim**

Contexto: plataforma financeira em que mfe-account guarda o saldo num estado global compartilhado, lido diretamente pelos outros MFEs. Ao incluir a moeda na estrutura do saldo, a lógica dos MFEs que liam o estado quebra.
Linha: `5,global-state-communication,"mfe-account, mfe-payments, mfe-dashboard",`

```csv
5,global-state-communication,"mfe-account, mfe-payments, mfe-dashboard",,Sim,
```

**Exemplo 6 — Global State Communication, não**

Contexto: a mesma plataforma, em que cada MFE tem estado local e os outros recebem o saldo por eventos publicados por mfe-account, com interface versionada.
Linha: `6,global-state-communication,"mfe-account, mfe-payments, mfe-dashboard",`

```csv
6,global-state-communication,"mfe-account, mfe-payments, mfe-dashboard",,Não,"Não há estado compartilhado acessado diretamente; a informação circula por eventos com contrato definido."
```

**Exemplo 7 — Mega Frontend, sim**

Contexto: e-commerce dividido em só dois MFEs: mfe-users (usuários) e mfe-shopping, que tem as telas de listagem de produtos, detalhe do produto, confirmação de compra e histórico de compras.
Linha: `7,mega-frontend,mfe-shopping,`

```csv
7,mega-frontend,mfe-shopping,,Sim,
```

**Exemplo 8 — Mega Frontend, não**

Contexto: o mesmo e-commerce, com mfe-products (listagem e detalhe, domínio de produto) e mfe-purchases (confirmação e histórico, domínio de compra).
Linha: `8,mega-frontend,mfe-products,`

```csv
8,mega-frontend,mfe-products,,Não,"Reúne só telas do domínio de produto; as responsabilidades de compra estão em outro MFE."
```

**Exemplo 9 — One Micro Frontend for All, sim**

Contexto: aplicação bancária em que mfe-accounts, mfe-cards e mfe-loans precisam de uma interface de transação, e os três importam diretamente um mesmo mfe-transactions, fortemente acoplado a eles.
Linha: `9,one-for-all,mfe-transactions,`

```csv
9,one-for-all,mfe-transactions,,Sim,
```

**Exemplo 10 — One Micro Frontend for All, não**

Contexto: a mesma aplicação, em que o mfe-transactions é uma caixa-preta: os MFEs disparam um evento openTransaction, ele se renderiza sozinho e devolve o resultado num evento transactionFinished, sem ser importado por ninguém.
Linha: `10,one-for-all,mfe-transactions,`

```csv
10,one-for-all,mfe-transactions,,Não,"Os outros MFEs não o importam; a interação é por eventos com entrada e saída definidas, preservando a independência."
```

**Exemplo 11 — Cyclic Dependency, sim**

Contexto: a tela de detalhe do produto, de mfe-products, integra fragmentos de mfe-checkout (carrinho), mfe-recommender (recomendações) e mfe-delivery (frete). Ao adicionar uma recomendação ao carrinho, mfe-recommender avisa mfe-checkout, que avisa mfe-delivery; quando o endereço muda, mfe-delivery avisa todos os outros para revalidarem seus produtos.
Linha: `11,cyclic-dependency,"mfe-recommender, mfe-checkout, mfe-delivery",`

```csv
11,cyclic-dependency,"mfe-recommender, mfe-checkout, mfe-delivery",,Sim,
```

**Exemplo 12 — Cyclic Dependency, não**

Contexto: a mesma tela, em que cada fragmento publica eventos num Event Store e só é notificado dos eventos que assina; nenhum MFE chama ou avisa outro diretamente.
Linha: `12,cyclic-dependency,"mfe-recommender, mfe-checkout, mfe-delivery",`

```csv
12,cyclic-dependency,"mfe-recommender, mfe-checkout, mfe-delivery",,Não,"Os MFEs não dependem uns dos outros; dependem de eventos centralizados, e nenhum precisa conhecer o outro."
```

**Exemplo 13 — Hub-like Dependency, sim**

Contexto: banco digital em que a tela principal, de um MFE, integra fragmentos de vários outros: lista de investimentos, gráfico do bitcoin, saldo da conta e fatura do cartão. Um erro em qualquer fragmento derruba a tela inteira.
Linha: `13,hub-like-dependency,mfe-home,`

```csv
13,hub-like-dependency,mfe-home,,Sim,
```

**Exemplo 14 — Hub-like Dependency, não**

Contexto: a mesma tela, em que cada fragmento trata os próprios erros e mostra uma mensagem de fallback quando indisponível, sem propagar o erro para a tela.
Linha: `14,hub-like-dependency,mfe-home,`

```csv
14,hub-like-dependency,mfe-home,,Não,"Os fragmentos degradam sozinhos; a falha de um não afeta a tela nem os outros, que é a consequência que a definição aponta."
```

# USER

Sistema: LBHackney-IT

microfrontends.json:
[{"id": "@mtfh/activity-history", "directory": "mtfh-frontend-activity-history", "entrypoint": "mtfh-frontend-activity-history/src/mtfh-activity-history.tsx", "routes": [], "role": "microfrontend", "mounts": [], "fragments": [], "screens": [{"component": "ActivitiesPersonView", "microfrontend": "@mtfh/activity-history", "route": "/activities/person/:id", "route_expression": "\"/activities/person/:id\"", "file": "mtfh-frontend-activity-history/src/views/activities-person-view/index.tsx", "line": 12, "reachable": true}, {"component": "ActivitiesTenureView", "microfrontend": "@mtfh/activity-history", "route": "/activities/tenure/:id", "route_expression": "\"/activities/tenure/:id\"", "file": "mtfh-frontend-activity-history/src/views/activities-tenure-view/index.tsx", "line": 15, "reachable": true}, {"component": "ActivitiesProcessView", "microfrontend": "@mtfh/activity-history", "route": "/activities/process/:processName/:id", "route_expression": "\"/activities/process/:processName/:id\"", "file": "mtfh-frontend-activity-history/src/views/activities-process-view/index.tsx", "line": 18, "reachable": true}, {"component": "ActivitiesPropertyView", "microfrontend": "@mtfh/activity-history", "route": "/activities/property/:id", "route_expression": "\"/activities/property/:id\"", "file": "mtfh-frontend-activity-history/src/views/activities-property-view/index.tsx", "line": 21, "reachable": true}], "size": {"files": 53, "lines": 3300, "code_lines": 3011}, "metadata": {"lifecycles": ["bootstrap", "mount", "unmount"], "active_when_form": "absent"}}, {"id": "@mtfh/processes", "directory": "mtfh-frontend-processes", "entrypoint": "mtfh-frontend-processes/src/mtfh-processes.tsx", "routes": [], "role": "microfrontend", "mounts": [], "fragments": [{"name": "locale", "microfrontend": "@mtfh/processes", "file": null, "line": 10}, {"name": "processes", "microfrontend": "@mtfh/processes", "file": null, "line": 10}], "screens": [{"component": "StartProcessView", "microfrontend": "@mtfh/processes", "route": "/processes/:processName/start/:targetType/:targetId", "route_expression": "\"/processes/:processName/start/:targetType/:targetId\"", "file": "mtfh-frontend-processes/src/views/index.ts", "line": 10, "reachable": true}, {"component": "ProcessesMenuView", "microfrontend": "@mtfh/processes", "route": "/processes/${targetType}/:id", "route_expression": "`/processes/${targetType}/:id`", "file": "mtfh-frontend-processes/src/views/index.ts", "line": 14, "reachable": true}, {"component": "ProcessLayout", "microfrontend": "@mtfh/processes", "route": "/processes/:processName/:processId", "route_expression": "\"/processes/:processName/:processId\"", "file": "mtfh-frontend-processes/src/views/process-view/process-layout.tsx", "line": 18, "reachable": true}], "size": {"files": 111, "lines": 7987, "code_lines": 7405}, "metadata": {"lifecycles": ["bootstrap", "mount", "unmount"], "active_when_form": "absent"}}, {"id": "@mtfh/property", "directory": "mtfh-frontend-property", "entrypoint": "mtfh-frontend-property/src/mtfh-property.tsx", "routes": [], "role": "microfrontend", "mounts": [], "fragments": [], "screens": [{"component": "AddBoilerHouseView", "microfrontend": "@mtfh/property", "route": "/property/:assetId/add-boiler-house", "route_expression": "\"/property/:assetId/add-boiler-house\"", "file": "mtfh-frontend-property/src/views/add-boiler-house-view/index.ts", "line": 34, "reachable": true}, {"component": "EditAssetOwnershipView", "microfrontend": "@mtfh/property", "route": "/property/:assetId/edit-asset-ownership", "route_expression": "\"/property/:assetId/edit-asset-ownership\"", "file": "mtfh-frontend-property/src/views/edit-asset-ownership-view/index.ts", "line": 37, "reachable": true}], "size": {"files": 87, "lines": 5156, "code_lines": 4625}, "metadata": {"lifecycles": ["bootstrap", "mount", "unmount"], "active_when_form": "absent"}}, {"id": "@mtfh/static", "directory": "mtfh-frontend-static", "entrypoint": "mtfh-frontend-static/src/mtfh-static.tsx", "routes": [], "role": "microfrontend", "mounts": [], "fragments": [], "screens": [{"component": "StaticView", "microfrontend": "@mtfh/static", "route": "/static", "route_expression": "\"/static\"", "file": "mtfh-frontend-static/src/views/static-view/index.ts", "line": 9, "reachable": true}], "size": {"files": 9, "lines": 121, "code_lines": 109}, "metadata": {"lifecycles": ["bootstrap", "mount", "unmount"], "active_when_form": "absent"}}, {"id": "@mtfh/worktray", "directory": "mtfh-frontend-worktray", "entrypoint": "mtfh-frontend-worktray/src/mtfh-worktray.tsx", "routes": [], "role": "microfrontend", "mounts": [], "fragments": [{"name": "WorktraySimpleList", "microfrontend": "@mtfh/worktray", "file": null, "line": 10}], "screens": [{"component": "WorktrayView", "microfrontend": "@mtfh/worktray", "route": "/", "route_expression": "\"/\"", "file": "mtfh-frontend-worktray/src/views/index.ts", "line": 8, "reachable": true}], "size": {"files": 35, "lines": 1717, "code_lines": 1553}, "metadata": {"lifecycles": ["bootstrap", "mount", "unmount"], "active_when_form": "absent"}}]

compositions.json:
[{"consumer": "@mtfh/worktray", "provider": "@mtfh/processes", "fragment": "processes", "local_name": "processesConfig", "imported_at": {"file": "mtfh-frontend-worktray/src/components/worktray-simple-list/worktray-simple-list.tsx", "line": 13, "code": "import { processes as processesConfig } from \"@mtfh/processes\";"}, "renders": []}, {"consumer": "@mtfh/worktray", "provider": "@mtfh/processes", "fragment": "processes", "local_name": "processes", "imported_at": {"file": "mtfh-frontend-worktray/src/components/worktray-list/worktray-list.tsx", "line": 14, "code": "import { processes } from \"@mtfh/processes\";"}, "renders": []}, {"consumer": "@mtfh/worktray", "provider": "@mtfh/processes", "fragment": "processes", "local_name": "processes", "imported_at": {"file": "mtfh-frontend-worktray/src/components/worktray-filters/worktray-filters.tsx", "line": 5, "code": "import { Process, processes } from \"@mtfh/processes\";"}, "renders": []}]

navigations.json:
[]

communications.json:
[]

api_calls.json:
[]

state_accesses.json:
[{"microfrontend": "@mtfh/processes", "library": "sessionStorage", "path": "person:heading", "at": {"file": "mtfh-frontend-processes/src/views/process-view/shared/contact-details-update-view/contact-details-update-dialog.tsx", "line": 52, "code": "sessionStorage.setItem(\"person:heading\", \"Person Updated\")"}, "access": "write"}]

Planilha a preencher:
#,anti-padrão,micro frontends,endpoint,julgamento (Sim/Não/Não sei),justificativa (se Não ou Não sei)
9,nano-frontend,worktray,,,
8,nano-frontend,static,,,
