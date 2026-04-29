# Etapa 08 - Validacao Final e Release Inicial

## Objetivo

Consolidar a entrega inicial com testes integrados, validacao dos criterios de
aceite, hardening de UX, documentacao operacional e preparo de release.

## Escopo

Inclui validacao ponta a ponta, revisao de seguranca, documentacao para usuario
e desenvolvedor, empacotamento e checklist de release.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E08-T01 | Criar matriz de aceite. | Checklist cobrindo RF01-RF33 e RNF01-RNF14. | Todos |
| E08-T02 | Criar testes integrados de inicializacao. | Execucao cria `.onbot-cli`, config, sessao e logs. | RF01, RF02, RF06, RF19 |
| E08-T03 | Criar teste integrado de fluxo de prompt. | Entrada do usuario, contexto, LLM fake, tool fake, resposta persistida e historico recente usado no turno seguinte. | RF03, RF04, RF05, RF06, RF19 |
| E08-T04 | Criar teste integrado de patch. | Plano, diff, permissao, aplicacao, hook e auditoria. | RF10, RF11, RF12, RF18, RF31 |
| E08-T05 | Criar teste integrado de comando local. | Classificacao, aprovacao, execucao, timeout e auditoria. | RF14, RF15, RF16, RF18 |
| E08-T06 | Criar teste integrado de Git. | Status, diff, branch e commit com confirmacao. | RF27 |
| E08-T07 | Criar teste integrado de extensibilidade. | Tool Python local, hook e comando customizado funcionando juntos. | RF25, RF26, RF31, RF32 |
| E08-T08 | Criar teste integrado de confirmacao pendente. | Agente pede continuacao, usuario responde `sim`, workflow anterior retoma; `nao` cancela sem nova tarefa. | RF18, RF19, RF30, RF33 |
| E08-T09 | Validar compatibilidade Windows. | Paths, comandos, cancelamento, confirmacoes e renderizacao testados no Windows. | RNF03 |
| E08-T10 | Validar compatibilidade Linux. | Paths, comandos, cancelamento, confirmacoes e renderizacao testados no Linux. | RNF03 |
| E08-T11 | Revisar mensagens e UX. | Erros, prompts de permissao, status, continuacoes e ajuda claros. | RNF14 |
| E08-T12 | Revisar privacidade e auditoria. | Confirmar redacao de segredos e rastreabilidade das acoes e pendencias. | RNF11, RNF12 |
| E08-T13 | Documentar configuracao de provedor. | Guia para `base_url`, `api_key_env`, `model` e parametros. | RF04, RF20, RF21 |
| E08-T14 | Documentar modos e permissoes. | Guia de `plan`, `default`, `accept_edits`, `trusted`, `locked`, `allow`, `ask`, `deny` e confirmacoes pendentes. | RF28, RF29, RF33 |
| E08-T15 | Documentar tools locais, hooks e comandos customizados. | Exemplos praticos e aviso de fronteira de confianca. | RF26, RF31, RF32, RNF04 |
| E08-T16 | Preparar release 0.1. | Versao, changelog, instrucoes de instalacao e validacao final. | RNF14 |

## Criterios de aceite

* Todos os requisitos funcionais possuem pelo menos uma validacao manual ou
  automatizada.
* Fluxos principais funcionam em ambiente limpo.
* Operacoes sensiveis sao confirmadas, bloqueadas ou auditadas conforme regra.
* Confirmacoes curtas retomam ou cancelam pendencias existentes, sem iniciar
  novos planos acidentais.
* Segredos nao aparecem em logs em cenarios comuns.
* A documentacao operacional permite instalar, configurar e usar a CLI.
* A versao 0.1 pode ser instalada e executada localmente.

## Testes recomendados

* Suite unitarias de todas as etapas anteriores.
* Testes integrados com diretorios temporarios.
* Testes com LLM fake para evitar dependencia externa.
* Testes de subprocesso para CLI real.
* Testes manuais em Windows e Linux.

## Riscos

* Cobrir apenas testes unitarios e perder falhas de integracao entre agente,
  permissoes, tools e storage.
* Documentar comportamento desejado que ainda nao esta implementado.
* Liberar sem validar os fluxos de cancelamento e erro, que sao criticos em CLI
  interativa.
