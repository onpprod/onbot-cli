# Etapa 04 - Seguranca, Permissoes e Execucao Controlada

## Objetivo

Implementar o nucleo de seguranca local: validacao de paths, modos de execucao,
regras de permissao, aprovacao do usuario, classificacao de comandos e execucao
controlada.

## Escopo

Inclui `Path Guard`, `Permission Manager`, `Approval Service`, `Command Policy`
e `Command Runner`.

Nao inclui sandbox para tools Python locais ou hooks, pois a arquitetura define
esses itens como codigo confiavel do usuario.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E04-T01 | Implementar `PathGuard`. | Normalizacao, resolucao absoluta, bloqueio de traversal e validacao dentro do workspace. | RF07, RF17 |
| E04-T02 | Implementar paths protegidos. | Regras para `.git/`, `.env`, chaves, logs e configs sensiveis. | RF12, RF13, RNF04, RNF11 |
| E04-T03 | Modelar acoes de permissao. | Tipos para file read/write, command, git, tool, hook e patch. | RF28 |
| E04-T04 | Implementar modos de execucao. | `plan`, `default`, `accept_edits`, `trusted` e `locked`. | RF29 |
| E04-T05 | Implementar precedencia de regras. | Avaliacao `deny > ask > allow > modo`. | RF28 |
| E04-T06 | Integrar `/mode`. | Consulta e troca do modo ativo durante a sessao. | RF29 |
| E04-T07 | Integrar `/permissions`. | Consulta e alteracao de regras durante a sessao. | RF28 |
| E04-T08 | Implementar `ApprovalService`. | Prompt explicito com acao, risco, alvo, decisao e registro. | RF18 |
| E04-T09 | Implementar `CommandPolicy`. | Classificacao `SAFE`, `CAUTION`, `DANGEROUS`, `BLOCKED`. | RF15, RF16 |
| E04-T10 | Implementar comandos bloqueados iniciais. | Bloqueio de exemplos como `rm -rf /`, `format`, `shutdown`, `reboot`. | RF16 |
| E04-T11 | Implementar `CommandRunner`. | Execucao local com cwd do workspace, timeout, stdout, stderr, exit code e cancelamento. | RF14, RF16, RF24 |
| E04-T12 | Auditar decisoes e execucoes. | Registros para permissoes, comandos, bloqueios e saidas. | RF19, RNF12 |

## Criterios de aceite

* Paths fora do workspace sao negados para tools internas.
* Traversal e symlinks sao tratados de forma segura.
* Modos de execucao produzem decisoes coerentes com a SRS.
* Regras `deny`, `ask` e `allow` respeitam a precedencia definida.
* Comandos bloqueados nao executam.
* Comandos permitidos registram stdout, stderr, exit code e decisao de
  permissao.

## Testes recomendados

* Paths relativos, absolutos, traversal e symlinks.
* Matriz de modos contra acoes de leitura, escrita, comando, Git e tool.
* Precedencia de regras com conflitos.
* Classificacao de comandos seguros, cautelosos, perigosos e bloqueados.
* Timeout e cancelamento do `CommandRunner`.

## Riscos

* Confundir sandbox logico das tools internas com sandbox de processo.
* Criar regras de comando por string simples demais e gerar falsos positivos ou
  falsos negativos perigosos.
* Bloquear o usuario em operacoes legitimas sem uma mensagem clara.

