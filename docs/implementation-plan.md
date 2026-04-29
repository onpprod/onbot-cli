# Planejamento de Implementacao - onbot-cli

## Objetivo

Este documento organiza a implementacao do `onbot-cli` em etapas incrementais,
com base em `docs/requirements.md` e `docs/architecture.md`.

O plano prioriza uma entrega segura e testavel:

1. Base do projeto e empacotamento.
2. Persistencia local e configuracao.
3. Interface interativa.
4. Seguranca, permissoes e execucao controlada.
5. Tools internas, contexto e patches.
6. LLM, agente, planner e workflows.
7. Continuidade conversacional, confirmacoes pendentes e retomada de workflows.
8. Git, hooks, tools locais e comandos customizados.
9. Validacao final e preparo de release.

## Documentos por etapa

| Etapa | Documento | Resultado esperado |
| --- | --- | --- |
| 01 | `docs/implementation-stage-01-foundation.md` | Projeto Python executavel, estrutura modular inicial e base de testes. |
| 02 | `docs/implementation-stage-02-workspace-storage.md` | `.onbot-cli`, config, sessoes, historico, cache e auditoria local. |
| 03 | `docs/implementation-stage-03-interactive-cli.md` | REPL interativo, slash commands internos e renderizacao Rich. |
| 04 | `docs/implementation-stage-04-security-permissions.md` | Path Guard, modos, regras, aprovacoes e comandos locais controlados. |
| 05 | `docs/implementation-stage-05-tools-context-patches.md` | Tool Registry, tools internas, Context Manager e Patch Service. |
| 06 | `docs/implementation-stage-06-agent-workflows-llm.md` | Cliente LLM, Agent Controller, Planner e workflows agenticos. |
| 06B | `docs/implementation-stage-06b-conversation-continuation.md` | Estado de turno, confirmacoes estruturadas e retomada de workflows. |
| 07 | `docs/implementation-stage-07-git-extensibility.md` | Git Service, hooks, tools Python locais e comandos customizados. |
| 08 | `docs/implementation-stage-08-validation-release.md` | Testes integrados, hardening, documentacao operacional e release inicial. |

A etapa 06B e uma etapa intermediaria adicionada para corrigir continuidade
conversacional antes das capacidades mutaveis da etapa 07. Ela nao renumera os
documentos 07 e 08 ja existentes.

## Marcos sugeridos

| Marco | Etapas | Descricao |
| --- | --- | --- |
| M0 - Base executavel | 01 | `onbot-cli` inicia e possui estrutura minima testavel. |
| M1 - CLI local persistente | 02, 03 | Sessao interativa persiste estado local e responde comandos internos. |
| M2 - Nucleo seguro | 04, 05 | Leitura, busca, patch e comandos seguem permissoes e auditoria. |
| M3 - Agente coerente | 06, 06B | LLM, planejamento, workflows e continuacoes de conversa operam sobre as primitivas seguras. |
| M4 - Produto extensivel | 07 | Git, hooks, tools locais e comandos customizados ficam disponiveis. |
| M5 - Release 0.1 | 08 | Criterios de aceite principais validados em Windows e Linux. |

## Regras de execucao do plano

* Cada etapa deve terminar com testes automatizados relevantes.
* Cada etapa deve preservar compatibilidade com Windows e Linux.
* As fronteiras de confianca definidas na arquitetura devem ser mantidas desde
  o inicio: tools internas protegidas, tools Python locais e hooks como codigo
  confiavel do usuario.
* Nenhuma etapa deve depender de modo batch, daemon, pipe ou GUI.
* Recursos complexos podem iniciar com implementacao minima, desde que o contrato
  publico e os testes permitam evolucao sem reescrita.

## Ordem de dependencias

```text
Etapa 01
  -> Etapa 02
    -> Etapa 03
      -> Etapa 04
        -> Etapa 05
          -> Etapa 06
            -> Etapa 06B
              -> Etapa 07
                -> Etapa 08
```

## Rastreabilidade geral

| Area | Requisitos principais | Etapas |
| --- | --- | --- |
| CLI interativa | RF01, RF03, RF24, RNF02, RNF14 | 01, 03 |
| Persistencia local | RF02, RF06, RF19, RF20, RF21, RNF05, RNF12, RNF13 | 02 |
| Seguranca e permissoes | RF07, RF12, RF13, RF15, RF16, RF17, RF18, RF28, RF29, RNF04, RNF11 | 04, 05 |
| Filesystem e contexto | RF08, RF09, RF10, RF11, RF22, RNF08, RNF09 | 05, 06 |
| LLM e agente | RF04, RF05, RF10, RF23, RF30 | 06 |
| Continuidade conversacional | RF06, RF18, RF19, RF30, RF33, RNF14 | 06B |
| Git | RF27 | 07 |
| Extensibilidade | RF25, RF26, RF31, RF32, RNF07 | 05, 07 |
| Testabilidade | RNF10 | Todas |
