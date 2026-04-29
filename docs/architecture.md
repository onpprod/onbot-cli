# Documento de Arquitetura - onbot-cli

## 1. Objetivo

Este documento define a arquitetura alvo do **onbot-cli**, uma CLI interativa
agentica para criacao de codigo.

A arquitetura foi derivada de `docs/requirements.md` e prioriza:

* modo exclusivamente interativo;
* workflows de desenvolvimento de software;
* integracao Git como capacidade central;
* sistema de permissoes com modos de execucao;
* seguranca por padrao para tools internas;
* tools Python locais como codigo confiavel do usuario;
* hooks e comandos customizados;
* persistencia local em `.onbot-cli`;
* modularidade para evolucao futura.

## 2. Contexto Arquitetural

O `onbot-cli` e iniciado pelo usuario dentro de um diretorio de projeto. Esse
diretorio passa a ser o **workspace** da sessao. O sistema conversa com o
usuario em um loop interativo, consulta um LLM, invoca tools, aplica patches,
executa comandos, opera Git e conduz workflows de codigo.

```text
Usuario
  |
  v
CLI Interativa
  |
  v
Command Router
  |
  +--> Comandos internos
  +--> Comandos customizados
  |
  v
Agent Controller
  |
  +--> Workflow Engine
  +--> Planner
  +--> Context Manager
  +--> LLM Client
  +--> Permission Manager
  +--> Tool Registry
  +--> Git Service
  +--> Hook Manager
  |
  v
Workspace local + .onbot-cli
```

## 3. Decisoes Arquiteturais

| Decisao | Justificativa |
| --- | --- |
| Apenas modo interativo | Atende a meta atual do produto e evita complexidade de batch, pipe e daemon. |
| Python como linguagem | Atende RNF01 e facilita integracao com Typer, Rich e prompt_toolkit. |
| Workflows como camada explicita | Transforma primitivas de leitura, patch e comando em jornadas de criacao de codigo. |
| Git como servico central | Suporta desenvolvimento real: status, diff, branch, commit e preparacao de mudancas. |
| Permissoes separadas do executor | Permite trocar modos sem espalhar regras por ferramentas individuais. |
| Tools internas protegidas por sandbox logico | Mantem seguranca para funcionalidades nativas do onbot-cli. |
| Tools Python locais como codigo confiavel | O usuario pediu extensibilidade sem limitacao; o sistema registra e expoe risco, mas nao sandboxa esse codigo. |
| Hooks como automacao confiavel do usuario | Hooks podem aplicar politicas e automacoes locais sem limitar o usuario. |
| Comandos customizados como prompts/workflows | Permite criar atalhos reutilizaveis como `/feature`, `/docs` e `/review`. |
| Persistencia local em `.onbot-cli` | Mantem estado, historico, logs, cache e extensoes junto ao workspace. |

## 4. Componentes Principais

### 4.1 CLI Application

Responsavel pelo ponto de entrada `onbot-cli`.

Responsabilidades:

* inicializar Typer;
* detectar o diretorio atual como workspace;
* carregar configuracoes local e global permitidas;
* criar a estrutura `.onbot-cli`;
* iniciar o loop interativo;
* encerrar a sessao com persistencia consistente.

### 4.2 Interactive Shell

Camada de interacao continua com o usuario usando `prompt_toolkit` e `Rich`.

Responsabilidades:

* capturar prompts;
* oferecer autocomplete para comandos internos e customizados;
* renderizar streaming do LLM;
* renderizar planos, diffs, permissoes, riscos, saidas e erros;
* trocar modo de execucao durante a sessao;
* lidar com cancelamento via terminal.

### 4.3 Command Router

Interpreta entradas iniciadas por `/`.

Responsabilidades:

* rotear comandos internos;
* expandir comandos customizados;
* validar argumentos;
* acionar workflows associados a comandos;
* exibir ajuda contextual.

Comandos internos minimos:

```text
/help
/exit
/clear
/status
/config
/tools
/permissions
/mode
/git
/hooks
/commands
/history
```

### 4.4 Agent Controller

Orquestrador principal da sessao.

Responsabilidades:

* manter estado da conversa;
* coordenar LLM, tools, Git, hooks e workflows;
* respeitar limite maximo de passos;
* pedir planejamento antes de acoes relevantes;
* executar ciclos de tentativa, validacao e correcao;
* registrar mensagens, acoes e resultados;
* retornar ao prompt apos conclusao, erro ou cancelamento.

### 4.5 Workflow Engine

Executa workflows agenticos compostos por etapas basicas.

Responsabilidades:

* mapear intencoes do usuario para workflows;
* executar etapas como requisitos, arquitetura, tasks, implementacao, testes e
  validacao;
* permitir que comandos customizados chamem workflows;
* registrar progresso;
* permitir intervencao do usuario entre etapas.

Workflows iniciais:

* desenvolvimento de feature;
* correcao de bug;
* refatoracao;
* criacao de documentacao;
* revisao de codigo;
* preparacao de commit.

### 4.6 Planner

Componente responsavel por planos de execucao.

Responsabilidades:

* transformar objetivo em passos;
* indicar arquivos provaveis;
* indicar riscos e validacoes;
* dividir trabalho em tasks pequenas;
* atualizar plano quando descobertas mudarem o escopo.

### 4.7 Context Manager

Controla quais dados entram no contexto do LLM.

Responsabilidades:

* montar resumo estrutural do projeto;
* limitar tamanho de arquivos;
* excluir arquivos sensiveis;
* selecionar trechos relevantes;
* cachear informacoes em `.onbot-cli/cache`;
* reduzir contexto apos etapas longas.

### 4.8 LLM Client

Interface unica para provedores OpenAI-compatible.

Responsabilidades:

* usar `base_url`, `api_key`, `model` e parametros configurados;
* suportar streaming;
* normalizar erros;
* nao registrar segredos;
* expor API estavel ao Agent Controller.

### 4.9 Permission Manager

Avalia permissoes para tools, comandos, arquivos, Git e hooks.

Responsabilidades:

* manter modo de execucao ativo;
* avaliar regras `deny`, `ask` e `allow`;
* aplicar precedencia `deny > ask > allow > modo`;
* proteger paths sensiveis;
* delegar confirmacao ao Approval Service;
* registrar decisoes.

### 4.10 Approval Service

Centraliza pedidos de confirmacao.

Responsabilidades:

* exibir acao proposta;
* exibir risco, diff, comando ou operacao Git;
* capturar decisao explicita;
* oferecer opcoes como permitir uma vez, permitir na sessao ou negar;
* registrar aprovacao ou rejeicao.

### 4.11 Path Guard

Servico usado por tools internas para validacao de paths.

Responsabilidades:

* normalizar paths;
* resolver paths absolutos;
* tratar symlinks;
* negar traversal;
* confirmar pertencimento ao workspace;
* proteger paths configurados.

O `Path Guard` nao e uma barreira de seguranca para tools Python locais ou
hooks do usuario.

### 4.12 Command Policy

Classifica e valida comandos executados pelo Command Runner.

Responsabilidades:

* classificar comandos como `SAFE`, `CAUTION`, `DANGEROUS` ou `BLOCKED`;
* bloquear comandos proibidos;
* reconhecer comandos de teste, lint, formatacao e build;
* identificar comandos destrutivos;
* produzir mensagem de risco compreensivel.

### 4.13 Command Runner

Executa comandos aprovados.

Responsabilidades:

* executar processos locais no workspace;
* capturar stdout, stderr e exit code;
* suportar timeout;
* suportar cancelamento;
* acionar hooks de pre e post execucao;
* registrar resultado.

### 4.14 Tool Registry

Catalogo de tools disponiveis para o agente.

Responsabilidades:

* registrar tools internas;
* registrar tools Python locais;
* expor catalogo para `/tools`;
* validar schema de entrada;
* indicar risco e origem;
* respeitar habilitacao/desabilitacao por configuracao.

### 4.15 Tool Loader

Carrega tools Python locais.

Responsabilidades:

* localizar modulos em paths configurados;
* ler manifestos YAML;
* reconhecer decorators;
* validar metadados obrigatorios;
* detectar nomes duplicados;
* registrar falhas de carregamento sem derrubar a CLI.

Tools Python locais rodam no mesmo processo ou ambiente configurado pelo
`onbot-cli` e sao consideradas codigo confiavel do usuario. O sistema nao deve
tentar impedir que esse codigo use `os`, `subprocess`, rede ou paths fora do
workspace.

### 4.16 Git Service

Camada de integracao com Git.

Responsabilidades:

* detectar repositorio;
* executar `status`, `diff` e listagem de arquivos alterados;
* criar branch;
* preparar mensagem de commit;
* executar commit apos permissao;
* classificar operacoes destrutivas ou remotas;
* registrar operacoes Git.

### 4.17 Patch Service

Gerencia propostas e aplicacao de alteracoes.

Responsabilidades:

* gerar e renderizar diff;
* validar paths via Path Guard para tools internas;
* aplicar patches conforme modo e permissoes;
* proteger paths configurados;
* registrar alteracoes.

### 4.18 Hook Manager

Executa hooks configurados pelo usuario.

Responsabilidades:

* carregar hooks de `.onbot-cli/hooks`;
* observar eventos do ciclo de vida;
* montar payload estruturado;
* executar script ou comando configurado;
* permitir resposta estruturada para permitir, negar, pedir confirmacao ou
  injetar contexto quando o evento suportar;
* registrar resultado.

Hooks sao codigo confiavel do usuario e nao sao sandboxados pelo `onbot-cli`.

### 4.19 Custom Command Manager

Gerencia comandos slash definidos pelo usuario.

Responsabilidades:

* carregar comandos de `.onbot-cli/commands`;
* validar nome, descricao e argumentos;
* expor comandos em `/commands` e autocomplete;
* expandir Markdown/YAML em prompt;
* acionar workflows associados.

### 4.20 Session Store

Persiste historico e estado.

Responsabilidades:

* criar identificador unico por sessao;
* gravar mensagens, actions, tool calls, comandos, Git, hooks e permissoes;
* permitir consulta por `/history`;
* manter dados em `.onbot-cli/sessions`.

### 4.21 Audit Logger

Registra eventos relevantes.

Responsabilidades:

* registrar comandos;
* registrar decisoes de permissao;
* registrar chamadas de tools;
* registrar hooks;
* registrar Git;
* registrar patches;
* mascarar segredos quando possivel.

## 5. Estrutura de Modulos Proposta

```text
src/onbot_cli/
  __init__.py
  cli.py
  app.py
  config.py
  workspace.py

  agent/
    __init__.py
    controller.py
    planner.py
    context.py
    workflows.py
    loop.py
    messages.py

  llm/
    __init__.py
    client.py
    openai_compatible.py
    streaming.py

  tools/
    __init__.py
    base.py
    registry.py
    loader.py
    manifest.py
    filesystem.py
    search.py
    patch.py
    command.py
    summary.py

  git/
    __init__.py
    service.py
    operations.py

  hooks/
    __init__.py
    manager.py
    models.py
    runner.py

  commands/
    __init__.py
    internal.py
    custom.py
    router.py

  security/
    __init__.py
    paths.py
    commands.py
    permissions.py
    approval.py
    redaction.py

  storage/
    __init__.py
    models.py
    sessions.py
    history.py
    logs.py

  ui/
    __init__.py
    repl.py
    renderers.py
    prompts.py

tests/
  unit/
  integration/
```

## 6. Persistencia Local

```text
.onbot-cli/
  config.yaml
  sessions/
    <session-id>.json
  history/
    commands.jsonl
  logs/
    onbot-cli.log
    audit.jsonl
  cache/
    project-summary.json
  tools/
    example_tool.py
    example_tool.yaml
  hooks/
    pre_tool_use.yaml
  commands/
    feature.md
    docs.md
```

### 6.1 Configuracao Local

```yaml
model:
  base_url: ""
  api_key_env: "OPENAI_API_KEY"
  model: ""
  temperature: 0.2

agent:
  max_steps: 20

workspace:
  max_file_size_kb: 256
  exclude:
    - ".git/"
    - ".onbot-cli/logs/"
    - "node_modules/"
    - ".venv/"

permissions:
  mode: "default"
  allow: []
  ask: []
  deny: []
  protected_paths:
    - ".git/"
    - ".env"
    - "*.pem"
    - "*.key"

git:
  enabled: true
  require_confirmation_for_remote: true
  require_confirmation_for_destructive: true

tools:
  enabled: []
  disabled: []
  paths:
    - ".onbot-cli/tools"

hooks:
  enabled: true
  paths:
    - ".onbot-cli/hooks"

commands:
  paths:
    - ".onbot-cli/commands"
```

## 7. Permissoes e Modos de Execucao

### 7.1 Precedencia

```text
deny > ask > allow > modo de execucao
```

### 7.2 Modos

| Modo | Politica |
| --- | --- |
| `plan` | Leitura, busca, resumo, Git status/diff e planejamento. Bloqueia escrita e comandos mutaveis. |
| `default` | Leitura livre para tools internas. Escrita, comandos, Git mutavel, hooks e tools de risco pedem confirmacao. |
| `accept_edits` | Edicoes no workspace sao aceitas, exceto paths protegidos. Comandos e Git mutavel seguem permissao. |
| `trusted` | Reduz prompts para acoes nao bloqueadas. Regras `deny` e paths protegidos continuam valendo para tools internas. |
| `locked` | Apenas acoes explicitamente permitidas por `allow` sao executadas. |

### 7.3 Avaliacao de Permissao

```text
1. Normalizar acao solicitada.
2. Verificar regra deny.
3. Verificar regra ask.
4. Verificar regra allow.
5. Aplicar politica do modo ativo.
6. Se necessario, chamar Approval Service.
7. Registrar decisao.
```

## 8. Workflows de Codigo

### 8.1 Etapas Basicas

O Workflow Engine deve compor workflows a partir destas etapas:

* entender objetivo;
* inspecionar projeto;
* criar ou revisar requisitos;
* criar ou revisar arquitetura;
* planejar tasks;
* implementar feature;
* refatorar feature;
* depurar erro;
* criar ou atualizar testes;
* rodar testes;
* rodar lint, formatacao ou build;
* validar resultado;
* revisar diff;
* atualizar documentacao;
* explicar mudancas.

### 8.2 Desenvolvimento de Feature

```text
1. Interpretar pedido.
2. Inspecionar estrutura e convencoes.
3. Criar ou revisar requisitos.
4. Criar ou revisar arquitetura.
5. Planejar tasks.
6. Implementar.
7. Refatorar quando houver ganho claro.
8. Criar ou atualizar testes.
9. Rodar validacoes.
10. Depurar falhas.
11. Revisar diff.
12. Explicar mudancas.
```

### 8.3 Criacao de Documentacao

```text
1. Identificar publico e objetivo.
2. Ler requisitos, arquitetura e codigo relevante.
3. Planejar estrutura.
4. Redigir documento.
5. Validar consistencia.
6. Atualizar referencias.
7. Explicar mudancas.
```

### 8.4 Correcao de Bug

```text
1. Coletar sintoma ou erro.
2. Reproduzir ou localizar evidencia.
3. Investigar causa raiz.
4. Planejar correcao minima.
5. Implementar.
6. Criar teste de regressao.
7. Rodar validacoes.
8. Explicar causa e solucao.
```

### 8.5 Refatoracao

```text
1. Definir escopo.
2. Rodar baseline de validacao.
3. Planejar passos pequenos.
4. Aplicar mudancas.
5. Rodar testes frequentemente.
6. Revisar diff.
7. Explicar riscos residuais.
```

### 8.6 Preparacao de Commit

```text
1. Consultar Git status.
2. Consultar diff.
3. Agrupar mudancas.
4. Rodar validacoes adequadas.
5. Preparar mensagem.
6. Solicitar confirmacao.
7. Criar commit.
8. Exibir resumo final.
```

## 9. Modelo de Tools

### 9.1 Contrato

```text
Tool
  name
  description
  input_schema
  risk_level
  origin
  execute(context, input) -> ToolResult
```

### 9.2 Tools Internas

Tools internas devem usar `ToolContext`, `Path Guard`, `Permission Manager`,
`Command Policy` e `Audit Logger`.

### 9.3 Tools Python Locais

Tools Python locais sao codigo confiavel do usuario.

Regras arquiteturais:

* o `onbot-cli` carrega apenas paths configurados;
* o catalogo mostra origem e risco;
* a invocacao e registrada;
* o `ToolContext` oferece helpers convenientes;
* o `ToolContext` nao e uma fronteira de seguranca;
* o sistema nao bloqueia filesystem, subprocessos, rede ou imports dentro da
  tool local.

Exemplo com decorator:

```python
from onbot_cli.tools import tool, ToolContext, ToolResult


@tool(
    name="read_todo_summary",
    description="Gera resumo dos TODOs do workspace.",
    risk="SAFE",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)
def run(context: ToolContext, path: str) -> ToolResult:
    target = context.paths.resolve(path)
    return ToolResult(output=target.read_text(encoding="utf-8"))
```

Exemplo com manifesto:

```yaml
name: "read_todo_summary"
description: "Gera resumo dos TODOs do workspace."
risk: "SAFE"
module: "todo_summary"
callable: "run"
input_schema:
  type: "object"
  properties:
    path:
      type: "string"
  required:
    - "path"
trusted: true
```

## 10. Hooks

Eventos suportados inicialmente:

```text
session_start
user_prompt_submit
pre_tool_use
post_tool_use
permission_request
file_changed
git_operation
session_end
```

Fluxo:

```text
1. Evento ocorre.
2. Hook Manager seleciona hooks ativos.
3. Hook Manager monta payload JSON.
4. Hook Runner executa comando/script configurado.
5. Resultado e interpretado quando o evento permitir decisao.
6. Resultado e registrado.
```

Hooks podem ser usados para:

* rodar formatadores apos edicao;
* bloquear prompts indesejados;
* exigir politicas especificas;
* adicionar contexto;
* registrar metricas externas.

Hooks sao responsabilidade do usuario e nao sao sandboxados.

## 11. Comandos Customizados

Comandos customizados ficam em `.onbot-cli/commands`.

Exemplo Markdown:

```markdown
---
name: feature
description: Planeja e implementa uma feature.
arguments:
  - name: descricao
    required: true
workflow: feature_development
---

Crie uma feature com a seguinte descricao:

{{ descricao }}
```

Fluxo:

```text
1. Usuario digita /feature "descricao".
2. Command Router encontra comando customizado.
3. Custom Command Manager valida argumentos.
4. Template e expandido.
5. Workflow Engine inicia workflow associado.
```

## 12. Git

O Git Service deve encapsular operacoes Git em vez de espalhar chamadas shell
pelo agente.

Operacoes iniciais:

* `status`;
* `diff`;
* `changed_files`;
* `create_branch`;
* `prepare_commit_message`;
* `commit`.

Operacoes destrutivas ou remotas devem passar por `Permission Manager`:

* `reset`;
* `clean`;
* `rebase`;
* `checkout` com perda de alteracoes;
* `branch -D`;
* `push`;
* `force push`.

## 13. Fluxos Principais

### 13.1 Inicializacao

```text
1. Usuario executa onbot-cli.
2. CLI resolve workspace.
3. Workspace Manager cria .onbot-cli.
4. Config Manager carrega configuracoes.
5. Permission Manager define modo inicial.
6. Tool Loader carrega tools.
7. Hook Manager carrega hooks.
8. Custom Command Manager carrega comandos.
9. Git Service detecta repositorio.
10. Session Store cria sessao.
11. Interactive Shell inicia loop.
```

### 13.2 Prompt do Usuario

```text
1. Shell recebe entrada.
2. Hooks user_prompt_submit podem inspecionar ou enriquecer contexto.
3. Command Router trata slash commands.
4. Agent Controller registra mensagem.
5. Context Manager monta contexto.
6. LLM Client responde em streaming.
7. Agent Controller executa tools/workflows conforme necessario.
8. Session Store e Audit Logger persistem eventos.
```

### 13.3 Invocacao de Tool

```text
1. Agente solicita tool.
2. Tool Registry valida existencia e schema.
3. Permission Manager avalia invocacao.
4. Hook pre_tool_use e executado.
5. Tool executa.
6. Hook post_tool_use e executado.
7. Resultado e registrado e retorna ao Agent Controller.
```

Para tools Python locais, o Permission Manager controla a invocacao da tool,
mas nao restringe o que o codigo da tool faz depois de iniciado.

### 13.4 Alteracao de Arquivo

```text
1. Agente propoe alteracao.
2. Patch Service gera diff.
3. Permission Manager avalia path, modo e regras.
4. Approval Service pede confirmacao quando necessario.
5. Patch Service aplica.
6. Hook file_changed pode executar.
7. Audit Logger registra.
```

### 13.5 Execucao de Comando

```text
1. Agente propoe comando.
2. Command Policy classifica risco.
3. Permission Manager avalia.
4. Approval Service pede confirmacao quando necessario.
5. Command Runner executa.
6. Saidas e exit code sao registrados.
```

### 13.6 Operacao Git

```text
1. Agente ou usuario solicita operacao Git.
2. Git Service normaliza a operacao.
3. Permission Manager avalia risco.
4. Hook git_operation pode inspecionar.
5. Approval Service pede confirmacao quando necessario.
6. Git Service executa.
7. Resultado e registrado.
```

## 14. Seguranca

### 14.1 Fronteiras de Confianca

| Item | Tratamento |
| --- | --- |
| Tools internas | Controladas por Path Guard, Permission Manager e Command Policy. |
| Command Runner | Controlado por Command Policy e Permission Manager. |
| Git Service | Controlado por Permission Manager. |
| Tools Python locais | Codigo confiavel do usuario, sem sandbox interno. |
| Hooks | Codigo confiavel do usuario, sem sandbox interno. |
| LLM | Nao recebe segredos deliberadamente sem necessidade ou permissao. |

### 14.2 Paths Protegidos

Paths protegidos devem exigir confirmacao ou bloqueio conforme regra ativa:

```text
.git/
.onbot-cli/config.yaml
.onbot-cli/logs/
.idea/
.vscode/
.env
*.pem
*.key
```

### 14.3 Comandos Bloqueados

Exemplos:

```text
rm -rf /
format
shutdown
reboot
```

## 15. Observabilidade e Auditoria

Eventos auditaveis:

* inicio e fim de sessao;
* prompts;
* comandos internos;
* comandos customizados;
* chamadas de tools;
* execucoes de hooks;
* decisoes de permissao;
* comandos shell;
* operacoes Git;
* patches;
* bloqueios de seguranca;
* erros de LLM.

Arquivos:

```text
.onbot-cli/logs/onbot-cli.log
.onbot-cli/logs/audit.jsonl
```

## 16. Testabilidade

Testes recomendados:

* `Path Guard`: paths relativos, absolutos, traversal e symlinks;
* `Permission Manager`: regras, precedencia e modos;
* `Command Policy`: classificacao de comandos;
* `Patch Service`: diff e aplicacao;
* `Git Service`: status, diff, commit e bloqueios;
* `Tool Loader`: manifesto, decorator e duplicidade;
* `Hook Manager`: eventos, payload e decisoes;
* `Custom Command Manager`: parsing, argumentos e expansao;
* `Workflow Engine`: feature, docs, bugfix, refactor e commit;
* `LLM Client`: transporte mockado;
* integracao: fluxo completo de feature com testes e Git diff.

## 17. Rastreabilidade com Requisitos

| Requisito | Atendido por |
| --- | --- |
| RF01 | CLI Application, Interactive Shell |
| RF02 | Workspace Manager, Config Manager |
| RF03 | Interactive Shell, Command Router |
| RF04 | LLM Client |
| RF05 | LLM Client, Interactive Shell |
| RF06 | Session Store |
| RF07 | Path Guard, tools internas |
| RF08 | Filesystem Tool, Context Manager, Permission Manager |
| RF09 | Filesystem Tool, Search Tool, Context Manager |
| RF10 | Planner, Workflow Engine |
| RF11 | Patch Service, UI Renderers |
| RF12 | Patch Service, Permission Manager, Approval Service |
| RF13 | Filesystem Tool, Patch Service, Permission Manager |
| RF14 | Command Runner, Command Policy |
| RF15 | Command Policy, Tool Registry |
| RF16 | Command Policy, Permission Manager |
| RF17 | Path Guard |
| RF18 | Approval Service, Permission Manager |
| RF19 | Audit Logger, Session Store |
| RF20 | Config Manager |
| RF21 | Config Manager |
| RF22 | Summary Tool, Context Manager |
| RF23 | Agent Controller |
| RF24 | Interactive Shell, Command Runner |
| RF25 | Tool Registry, Tool Loader |
| RF26 | Tool Loader, Tool Registry |
| RF27 | Git Service |
| RF28 | Permission Manager |
| RF29 | Permission Manager, Interactive Shell |
| RF30 | Workflow Engine, Planner |
| RF31 | Hook Manager |
| RF32 | Custom Command Manager, Command Router |
| RNF01 | Python package under `src/onbot_cli` |
| RNF02 | Typer, Rich, prompt_toolkit |
| RNF03 | Path Guard, Command Policy, Git Service |
| RNF04 | Security layer and trust-boundary model |
| RNF05 | Audit Logger and local logs |
| RNF06 | Module boundaries |
| RNF07 | Tool Loader and Tool Registry |
| RNF08 | Context Manager and cache |
| RNF09 | Context Manager |
| RNF10 | Isolated services and mockable dependencies |
| RNF11 | Redaction and sensitive-file policy |
| RNF12 | Audit Logger |
| RNF13 | `.onbot-cli` storage |
| RNF14 | Interactive Shell and renderers |

## 18. Criterios Arquiteturais de Aceite

A implementacao estara alinhada a esta arquitetura quando:

* iniciar com `onbot-cli` em modo interativo;
* criar e usar `.onbot-cli`;
* suportar comandos internos essenciais;
* suportar modos `plan`, `default`, `accept_edits`, `trusted` e `locked`;
* suportar regras `allow`, `ask` e `deny`;
* impedir tools internas de sair do workspace;
* carregar tools Python locais como codigo confiavel do usuario;
* suportar hooks;
* suportar comandos customizados;
* conduzir workflows de feature, docs, bugfix, refactor e commit;
* integrar com Git para status, diff, branch e commit;
* executar comandos com classificacao de risco;
* aplicar patches conforme permissoes;
* registrar sessoes, auditoria, hooks, tools, comandos e Git;
* comunicar-se com provedores OpenAI-compatible via streaming;
* possuir testes automatizados para permissoes, Git, tools, hooks, comandos e
  workflows criticos.
