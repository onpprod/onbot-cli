# Etapa 01 - Fundacao do Projeto

## Objetivo

Criar a base executavel e testavel do `onbot-cli`, respeitando a estrutura
modular definida na arquitetura.

## Escopo

Inclui empacotamento Python, dependencias iniciais, ponto de entrada da CLI,
estrutura de modulos e configuracao minima de testes.

Nao inclui ainda comunicacao com LLM, permissoes completas, tools, Git, hooks ou
workflows agenticos.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E01-T01 | Revisar `pyproject.toml` e definir dependencias base. | Dependencias para `typer`, `rich`, `prompt_toolkit`, `pyyaml` e `pytest` declaradas. | RNF01, RNF02, RNF10 |
| E01-T02 | Configurar script de entrada `onbot-cli`. | Comando `onbot-cli` apontando para `onbot_cli.cli:app`. | RF01 |
| E01-T03 | Criar estrutura de pacotes em `src/onbot_cli`. | Modulos `agent`, `commands`, `config`, `git`, `hooks`, `llm`, `security`, `storage`, `tools`, `ui` e `workspace`. | RNF06 |
| E01-T04 | Implementar bootstrap minimo da aplicacao. | CLI inicia, detecta o diretorio atual e mostra uma saida minima controlada. | RF01 |
| E01-T05 | Criar contratos e modelos base compartilhados. | Tipos iniciais para resultado de comando, erro de aplicacao, workspace e contexto. | RNF06, RNF10 |
| E01-T06 | Configurar testes unitarios basicos. | `tests/unit` com teste de importacao, versao e bootstrap. | RNF10 |
| E01-T07 | Definir convencoes de erro e retorno. | Excecoes de dominio e mensagens padronizadas para CLI. | RNF14 |
| E01-T08 | Criar README tecnico minimo. | Instrucoes de instalacao local e execucao em desenvolvimento. | RNF14 |

## Criterios de aceite

* `onbot-cli` pode ser executado a partir do ambiente de desenvolvimento.
* O pacote `onbot_cli` importa sem efeitos colaterais pesados.
* A estrutura modular principal existe.
* Testes basicos passam localmente.
* A CLI ainda opera apenas em modo interativo ou prepara esse modo, sem criar
  interface batch.

## Testes recomendados

* Importacao de `onbot_cli`.
* Instanciacao do app Typer.
* Resolucao do diretorio atual como workspace.
* Verificacao do script de entrada no pacote.

## Riscos

* Travar cedo demais uma API interna sem validar os fluxos reais.
* Declarar dependencias demais antes de haver necessidade concreta.
* Misturar responsabilidades de UI, agente e storage no bootstrap inicial.

