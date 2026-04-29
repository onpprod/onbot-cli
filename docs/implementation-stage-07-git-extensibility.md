# Etapa 07 - Git, Hooks, Tools Locais e Comandos Customizados

## Objetivo

Adicionar as capacidades centrais de produto que tornam o `onbot-cli`
adequado ao desenvolvimento real: Git, hooks, tools Python locais e comandos
slash customizados.

## Escopo

Inclui `Git Service`, `Tool Loader`, `Hook Manager`, `Custom Command Manager` e
integracao desses componentes ao agente, permissoes, auditoria e UI.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E07-T01 | Implementar deteccao de repositorio Git. | Identificar repo, branch atual e disponibilidade de Git. | RF27 |
| E07-T02 | Implementar operacoes Git seguras. | `status`, `diff` e `changed_files` sem mutacao. | RF27 |
| E07-T03 | Implementar operacoes Git mutaveis. | `create_branch`, `prepare_commit_message` e `commit` com permissao. | RF27, RF18, RF28 |
| E07-T04 | Proteger operacoes Git destrutivas/remotas. | `reset`, `clean`, `rebase`, `checkout` com perda, `branch -D`, `push` e force push exigem confirmacao ou bloqueio. | RF27, RF18 |
| E07-T05 | Integrar `/git`. | Exibir status, diff resumido, branch e comandos suportados. | RF03, RF27 |
| E07-T06 | Implementar manifesto de tool local. | Parser YAML com `name`, `description`, `risk`, `module`, `callable`, `input_schema`, `trusted`. | RF26 |
| E07-T07 | Implementar decorator de tool local. | Registro por decorator em modulo Python carregado de path configurado. | RF26, RNF07 |
| E07-T08 | Implementar `ToolLoader`. | Carregar paths configurados, detectar duplicidade e registrar falhas sem derrubar a CLI. | RF26 |
| E07-T09 | Marcar fronteira de confianca das tools locais. | UI e auditoria indicam que tools Python locais sao codigo confiavel do usuario. | RF26, RNF04 |
| E07-T10 | Implementar modelos de hook. | YAML com `name`, `event`, `command` e `enabled`. | RF31 |
| E07-T11 | Implementar `HookManager` e `HookRunner`. | Carregar hooks, montar payload JSON, executar comando/script e registrar resultado. | RF31 |
| E07-T12 | Integrar eventos de hook. | `session_start`, `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `permission_request`, `file_changed`, `git_operation`, `session_end`. | RF31 |
| E07-T13 | Integrar `/hooks`. | Listar hooks, status, eventos e ultimos resultados. | RF03, RF31 |
| E07-T14 | Implementar comandos customizados Markdown/YAML. | Parser de front matter, argumentos, prompt e workflow associado. | RF32 |
| E07-T15 | Implementar expansao de template. | Substituir argumentos e gerar prompt/workflow reutilizavel. | RF32 |
| E07-T16 | Integrar `/commands` e autocomplete. | Listar comandos customizados e sugerir nomes no prompt. | RF03, RF32 |
| E07-T17 | Conectar extensoes ao agente. | Tools locais, hooks e comandos customizados passam pelo fluxo de permissao, auditoria e contexto. | RF19, RF25, RF28, RF31, RF32 |

## Criterios de aceite

* Git status, diff e arquivos alterados funcionam em repositorio Git.
* Operacoes Git mutaveis exigem permissao conforme modo e regra.
* Tools Python locais podem ser carregadas por manifesto ou decorator.
* Falhas em tools locais nao derrubam a CLI.
* Hooks sao executados nos eventos suportados e recebem payload estruturado.
* Comandos customizados aparecem em `/commands` e no autocomplete.
* Um comando customizado pode expandir prompt e acionar workflow.

## Testes recomendados

* Git em repositorio temporario.
* Bloqueio ou confirmacao de operacoes destrutivas/remotas.
* Tool local valida, invalida e duplicada.
* Manifesto YAML com schema incorreto.
* Hook com sucesso, falha e resposta estruturada.
* Comando customizado com argumento obrigatorio, ausente e template expandido.

## Riscos

* Executar hooks ou tools locais sem deixar claro que sao codigo confiavel do
  usuario.
* Deixar chamadas Git espalhadas pelo agente em vez de centralizar no
  `Git Service`.
* Permitir que comandos customizados ignorem workflows, permissoes ou auditoria.

