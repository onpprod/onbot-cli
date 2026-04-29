# Etapa 06B - Continuidade Conversacional e Confirmacoes Pendentes

## Objetivo

Corrigir a lacuna entre respostas do LLM e estado real do agente: quando o
agente pedir confirmacao, continuar, cancelar ou escolher uma opcao, a proxima
entrada do usuario deve ser interpretada como resposta a uma interacao pendente,
e nao como uma nova tarefa sem contexto.

## Motivacao

A etapa 06 introduz o primeiro ciclo agentico com LLM, planner e workflows, mas
ainda permite que o modelo escreva perguntas em texto livre como "posso
continuar?" sem registrar essa pergunta como estado de controle. Nesse caso,
uma resposta curta como `sim` pode virar um novo objetivo e gerar um novo plano
com objetivo `sim`.

Isso e incorreto para a experiencia do produto e perigoso antes das etapas que
executarao Git, hooks, comandos customizados e actions mutaveis. Confirmacoes
precisam ser estruturadas, auditaveis e roteadas pelo controlador, nao inferidas
a partir de texto livre do LLM.

## Escopo

Inclui estado de turno, historico conversacional controlado, interacoes
pendentes, confirmacoes estruturadas, retomada de workflow e integracao com
`ApprovalService`. Inclui tambem a aplicacao real de acoes estruturadas de
arquivo propostas pelo LLM: criar, editar, mover e excluir arquivos dentro do
workspace.

Nao inclui ainda Git completo, hooks reais, tools Python locais ou comandos
customizados carregados do workspace.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E06B-T01 | Modelar estado de turno do agente. | Tipos para `idle`, `running`, `awaiting_confirmation`, `awaiting_choice`, `cancelled`, `completed` e `failed`. | RF06, RF19, RF33 |
| E06B-T02 | Modelar interacao pendente. | Estrutura com `id`, tipo, prompt exibido, workflow, passo atual, payload, opcoes aceitas, expiracao e acao de retomada. | RF18, RF19, RF33 |
| E06B-T03 | Persistir e limpar pendencias da sessao. | Pendencias gravadas na sessao e removidas apos aprovacao, rejeicao, cancelamento ou conclusao. | RF06, RF19 |
| E06B-T04 | Implementar roteamento de continuacao no REPL. | Entradas como `sim`, `nao`, `continuar`, `cancelar` e escolhas numericas respondem a pendencias antes de criar novo turno. | RF03, RF18, RF33, RNF14 |
| E06B-T05 | Usar historico recente no contexto do turno. | O AgentController monta o proximo request com resumo do estado e mensagens recentes relevantes. | RF06, RF10, RF30, RF33 |
| E06B-T06 | Separar plano proposto de autorizacao real. | O LLM pode explicar um plano, mas permissoes para comandos, patches, Git, hooks e tools mutaveis passam somente por `ApprovalService`. | RF18, RF28, RF33 |
| E06B-T07 | Criar API de retomada de workflow. | `WorkflowEngine` permite pausar, retomar, cancelar e registrar progresso por etapa. | RF30, RF33 |
| E06B-T08 | Bloquear confirmacoes fantasma. | Se nao houver pendencia, respostas curtas como `sim` ou `nao` nao devem acionar plano amplo sem contexto; devem pedir esclarecimento ou ser tratadas como prompt comum explicitamente. | RF33, RNF14 |
| E06B-T09 | Integrar prompt engineering com regras testaveis. | System prompt instrui o LLM a nao solicitar autorizacao em texto livre para acoes mutaveis; o codigo continua sendo a fonte de verdade. | RF18, RNF11, RF33 |
| E06B-T10 | Auditar decisao de continuacao. | Registrar pergunta, resposta, decisao, pendencia resolvida e proximo passo. | RF19, RF33 |
| E06B-T11 | Definir protocolo de acoes de arquivo do agente. | JSON estruturado para `create_file`, `write_file`, `edit_file`, `move_file` e `delete_file`, separado da resposta em texto. | RF11, RF12, RF13, RF18, RF33 |
| E06B-T12 | Aplicar acoes reais de arquivo apos confirmacao. | Criar/editar via `PatchService`; mover/excluir via `PathGuard`, `PermissionManager`, hooks e auditoria. | RF12, RF13, RF17, RF18, RF19, RF33 |

## Criterios de aceite

* Se o agente perguntar se deve continuar e o usuario responder `sim`, o
  workflow anterior e retomado.
* Se o usuario responder `nao` ou `cancelar`, a pendencia e encerrada sem criar
  nova tarefa.
* Uma entrada curta como `sim` sem pendencia ativa nao vira automaticamente um
  novo plano com objetivo `sim`.
* Acoes mutaveis continuam passando por `PermissionManager` e
  `ApprovalService`; o texto do LLM nunca concede permissao por conta propria.
* O historico recente e o estado pendente entram no contexto do proximo turno de
  forma limitada e redigida.
* Pendencias e decisoes aparecem na sessao e na auditoria local.
* Workflows podem pausar e retomar em etapas previsiveis.
* O agente consegue criar, editar, mover e excluir arquivos reais no workspace
  quando recebe uma acao estruturada valida e o usuario confirma.
* A resposta textual do LLM nao e tratada como alteracao aplicada; somente o
  executor de acoes de arquivo pode materializar mudancas.

## Testes recomendados

* REPL com LLM fake que solicita continuacao; entrada `sim` retoma o workflow
  anterior.
* REPL com pendencia ativa e entrada `nao`; workflow e cancelado e nenhuma nova
  chamada LLM e criada para objetivo `nao`.
* Entrada `sim` sem pendencia ativa produz pedido de esclarecimento ou prompt
  comum controlado, mas nao executa workflow amplo.
* `ApprovalService` com acao mutavel aprovada e negada.
* Persistencia de pendencia em sessao e limpeza apos decisao.
* Contexto do segundo turno contem resumo do turno anterior sem segredos.
* `agent.max_steps` continua sendo respeitado ao retomar workflows.
* Criacao real de arquivo apos `sim`.
* Edicao real de arquivo apos `sim`.
* Movimentacao real de arquivo apos `sim`.
* Exclusao real de arquivo apos `sim`.
* Resposta `nao` cancela a pendencia sem alterar arquivos.

## Impacto nas etapas seguintes

* A etapa 07 deve usar a API de pendencias/confirmacoes para Git mutavel, hooks,
  tools locais e comandos customizados, em vez de criar prompts ad hoc.
* A etapa 08 deve validar fluxos multi-turn e nao apenas prompts isolados.
* Qualquer workflow que solicite "continuar" deve registrar uma interacao
  pendente antes de devolver o prompt ao usuario.

## Riscos

* Duplicar semantica entre `ApprovalService` e confirmacoes de workflow.
* Persistir contexto demais e expor informacao sensivel em sessoes.
* Fazer heuristicas de `sim`/`nao` globais demais e capturar prompts legitimos
  do usuario sem pendencia ativa.
