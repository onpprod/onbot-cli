# Etapa 03 - CLI Interativa e Comandos Internos

## Objetivo

Implementar a experiencia interativa basica do `onbot-cli`: loop continuo,
slash commands, autocomplete inicial e renderizacao no terminal.

## Escopo

Inclui `Interactive Shell`, `Command Router`, comandos internos minimos e
renderizadores Rich.

Nao inclui ainda execucao agentica completa, tools reais, patches aplicados ou
operacoes Git mutaveis.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E03-T01 | Implementar loop interativo com `prompt_toolkit`. | Prompt continuo, leitura de entrada e encerramento controlado. | RF01, RF03, RNF02, RNF14 |
| E03-T02 | Implementar cancelamento local. | Tratamento de `Ctrl+C` e `Ctrl+D` sem corromper sessao. | RF24 |
| E03-T03 | Criar `CommandRouter`. | Roteamento de entradas iniciadas por `/`. | RF03 |
| E03-T04 | Implementar `/help` e `/exit`. | Ajuda contextual e encerramento persistente da sessao. | RF03 |
| E03-T05 | Implementar `/clear`, `/status` e `/history`. | Limpeza visual, status do workspace e consulta de historico. | RF03, RF06 |
| E03-T06 | Implementar `/config`. | Exibicao segura de configuracao ativa, com segredos mascarados. | RF20, RF21, RNF11 |
| E03-T07 | Implementar comandos de consulta stubados. | `/tools`, `/permissions`, `/mode`, `/git`, `/hooks`, `/commands` conectados a contratos de servico. | RF03 |
| E03-T08 | Criar autocomplete inicial. | Sugestoes para comandos internos e, depois, customizados. | RF03, RF32, RNF14 |
| E03-T09 | Criar renderizadores Rich. | Tabelas, paineis simples, erros, planos, diffs e prompts de aprovacao. | RNF02, RNF14 |
| E03-T10 | Registrar entradas do usuario. | Prompts e comandos persistidos na sessao e no historico. | RF06, RF19 |

## Criterios de aceite

* `onbot-cli` abre um prompt interativo.
* Comandos internos minimos respondem sem derrubar a sessao.
* `/exit` encerra persistindo a sessao.
* Erros de comando sao exibidos de forma clara.
* Historico local registra os comandos executados.
* A interface nao depende de modo batch, pipe ou daemon.

## Testes recomendados

* Testes unitarios do `CommandRouter`.
* Testes de parsing de argumentos de slash commands.
* Testes de renderizadores com saida capturada.
* Testes de encerramento e persistencia da sessao.

## Riscos

* Fazer a UI conhecer detalhes internos de cada servico.
* Deixar comandos internos com comportamentos diferentes do que os servicos
  reais entregarao nas etapas seguintes.
* Nao tratar cancelamento desde cedo, dificultando comandos longos depois.

