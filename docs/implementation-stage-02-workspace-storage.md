# Etapa 02 - Workspace, Configuracao e Persistencia

## Objetivo

Implementar a estrutura local `.onbot-cli` e os servicos de configuracao,
historico, sessoes, cache e auditoria.

## Escopo

Inclui criacao do workspace local, leitura e escrita de configuracao, modelos de
persistencia, logs locais e redacao basica de segredos.

Nao inclui ainda execucao de tools, comandos shell reais, Git mutavel ou chamada
ao LLM.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E02-T01 | Implementar `WorkspaceManager`. | Resolucao do workspace e criacao idempotente de `.onbot-cli`. | RF02, RNF13 |
| E02-T02 | Criar arvore local padrao. | Pastas `sessions`, `history`, `logs`, `cache`, `tools`, `hooks`, `commands`. | RF02 |
| E02-T03 | Implementar `ConfigManager`. | Leitura, defaults e escrita de `.onbot-cli/config.yaml`. | RF20 |
| E02-T04 | Preparar suporte a configuracao global. | Leitura opcional de config global apenas para provedores, modelos e preferencias nao sensiveis. | RF21 |
| E02-T05 | Modelar dados de sessao. | Estrutura para mensagens, actions, tool calls, comandos, Git, permissoes e hooks. | RF06, RF19 |
| E02-T06 | Implementar `SessionStore`. | Criacao de ID de sessao e persistencia em `.onbot-cli/sessions/<id>.json`. | RF06 |
| E02-T07 | Implementar historico de comandos. | Registro append-only em `.onbot-cli/history/commands.jsonl`. | RF03, RF19 |
| E02-T08 | Implementar `AuditLogger`. | Eventos em `.onbot-cli/logs/audit.jsonl` e log operacional em `onbot-cli.log`. | RF19, RNF05, RNF12 |
| E02-T09 | Implementar redacao de segredos. | Mascarar chaves, tokens e valores sensiveis em logs quando possivel. | RNF11, RNF12 |
| E02-T10 | Criar cache estrutural inicial. | Arquivo `cache/project-summary.json` com contrato de leitura e escrita. | RF22, RNF08 |

## Criterios de aceite

* A primeira execucao cria `.onbot-cli` com a estrutura minima.
* A criacao e idempotente e nao sobrescreve config existente sem necessidade.
* Configuracao local e defaults sao carregados de forma previsivel.
* Uma sessao pode ser criada, atualizada e lida novamente.
* Eventos de auditoria sao gravados com timestamp e tipo.
* Segredos obvios nao aparecem em claro nos logs gerados pelo sistema.

## Testes recomendados

* Criacao de workspace em diretorio temporario.
* Merge de configuracao default, local e global.
* Escrita e leitura de sessao.
* Escrita append-only de historico e auditoria.
* Redacao de campos como `api_key`, `token`, `authorization` e `.env`.

## Riscos

* Acoplar formato de storage ao formato exibido na UI.
* Permitir que logs crescam sem limite ja na primeira versao.
* Registrar prompts ou configs com dados sensiveis sem redacao.

