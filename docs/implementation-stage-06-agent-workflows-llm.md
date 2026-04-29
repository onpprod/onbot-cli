# Etapa 06 - LLM, Agent Controller, Planner e Workflows

## Objetivo

Implementar o nucleo agentico: cliente LLM OpenAI-compatible, streaming,
controle de passos, planejamento e workflows de desenvolvimento.

## Escopo

Inclui `LLM Client`, `Agent Controller`, `Planner`, modelos de mensagem e
`Workflow Engine`.

Nao inclui ainda Git completo, hooks reais, tools Python locais ou comandos
customizados carregados do workspace. A continuidade conversacional completa,
incluindo confirmacoes pendentes e retomada de workflows apos respostas como
`sim` ou `nao`, fica na etapa 06B.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E06-T01 | Implementar configuracao de provedor LLM. | `base_url`, `api_key_env`, `model`, temperatura e parametros de geracao. | RF04, RF20, RF21 |
| E06-T02 | Implementar cliente OpenAI-compatible. | Interface unica para request, streaming, erro normalizado e cancelamento. | RF04, RF05, RF24 |
| E06-T03 | Proteger segredos do provedor. | API keys nao aparecem em logs, historico ou renderizacao. | RNF11 |
| E06-T04 | Modelar mensagens do agente. | Mensagens de usuario, assistente, sistema, tool call e resultado. | RF06, RF19 |
| E06-T05 | Implementar `AgentController`. | Orquestrar contexto, LLM, tools, permissoes, storage e UI. | RF10, RF19, RF23 |
| E06-T06 | Aplicar limite de passos. | `agent.max_steps` interrompe loops longos com mensagem clara. | RF23 |
| E06-T07 | Implementar `Planner`. | Plano com objetivo, areas provaveis, passos, riscos, validacoes e criterio de conclusao. | RF10 |
| E06-T08 | Implementar `WorkflowEngine`. | Composicao de etapas basicas reutilizaveis. | RF30 |
| E06-T09 | Criar workflow de feature. | Entender, inspecionar, planejar, implementar, testar, revisar e explicar. | RF30 |
| E06-T10 | Criar workflow de bugfix. | Reproduzir/localizar, investigar, corrigir, testar regressao e explicar. | RF30 |
| E06-T11 | Criar workflow de refatoracao. | Baseline, passos pequenos, validacoes frequentes e revisao de diff. | RF30 |
| E06-T12 | Criar workflow de documentacao. | Ler base, planejar estrutura, redigir, validar consistencia e explicar. | RF30 |
| E06-T13 | Criar workflow de revisao de codigo. | Inspecionar diff/codigo, apontar riscos e sugerir validacoes. | RF30 |
| E06-T14 | Criar workflow de preparacao de commit inicial. | Preparar mensagem e resumo usando status/diff quando Git estiver disponivel. | RF30 |
| E06-T15 | Integrar streaming na UI. | Renderizacao incremental da resposta do modelo. | RF05, RNF14 |
| E06-T16 | Preparar ponto de extensao para estado de turno. | Contratos do controller permitem evoluir para pendencias e retomada sem reescrever LLM/workflows. | RF06, RF19, RF33 |

## Criterios de aceite

* A CLI conversa com um provedor OpenAI-compatible configurado.
* Respostas sao exibidas em streaming.
* O agente monta contexto limitado e invoca tools internas via registry.
* Antes de acoes relevantes, um plano estruturado e produzido.
* O limite maximo de passos impede loops indefinidos.
* Workflows minimos existem e podem ser acionados internamente.
* Perguntas de confirmacao emitidas pelo LLM ainda nao concedem permissao nem
  retomam workflow por si so; esse comportamento e fechado na etapa 06B.

## Testes recomendados

* Cliente LLM com transporte mockado.
* Streaming com chunks simulados.
* Agent Controller com LLM fake e tools fake.
* Planner com entradas representativas.
* Workflow Engine executando etapas em ordem e registrando progresso.
* Interrupcao por `max_steps`.
* Regressao documentada para resposta curta `sim` antes da etapa 06B.

## Riscos

* Deixar o LLM decidir acoes sem passar pelos servicos de seguranca.
* Misturar prompt engineering com regras de dominio que deveriam estar em
  codigo testavel.
* Criar workflows rigidos demais para tarefas reais de desenvolvimento.
* Permitir que uma pergunta textual do modelo seja confundida com uma
  confirmacao estruturada do sistema.
