# Etapa 05 - Tools Internas, Contexto e Patches

## Objetivo

Implementar as primitivas seguras usadas pelo agente: catalogo de tools,
filesystem, busca, resumo de projeto, contexto e aplicacao controlada de
patches.

## Escopo

Inclui `Tool Registry`, contrato de tool, tools internas iniciais,
`Context Manager` e `Patch Service`.

Nao inclui ainda carregamento de tools Python locais do usuario, que fica na
etapa de extensibilidade.

## Tarefas

| ID | Tarefa | Entrega | Requisitos |
| --- | --- | --- | --- |
| E05-T01 | Definir contrato `Tool`. | `name`, `description`, `input_schema`, `risk_level`, `origin` e `execute`. | RF25 |
| E05-T02 | Implementar `ToolResult` e `ToolContext`. | Resultado padronizado e acesso a workspace, config, auditoria e seguranca. | RF25, RNF06 |
| E05-T03 | Implementar `ToolRegistry`. | Registro, listagem, habilitacao, desabilitacao e validacao de schema. | RF25 |
| E05-T04 | Integrar `/tools`. | Exibir nome, descricao, origem, risco e entradas esperadas. | RF25 |
| E05-T05 | Criar tool interna de listagem. | Listar arquivos respeitando exclusoes, tamanho e Path Guard. | RF08, RF09 |
| E05-T06 | Criar tool interna de leitura. | Ler arquivos com limite de tamanho, paths sensiveis e permissoes. | RF08 |
| E05-T07 | Criar tool interna de busca textual. | Busca por texto e padroes de arquivo dentro do workspace. | RF09 |
| E05-T08 | Criar tool interna de resumo. | Detectar arvore relevante, linguagens, dependencias e comandos provaveis. | RF22, RNF08 |
| E05-T09 | Implementar `ContextManager`. | Selecionar trechos relevantes, aplicar limites e cachear resumo estrutural. | RF10, RF22, RNF08, RNF09 |
| E05-T10 | Implementar `PatchService`. | Gerar diff, validar paths, aplicar alteracoes e registrar auditoria. | RF11, RF12, RF13 |
| E05-T11 | Conectar tools ao `PermissionManager`. | Invocacoes internas passam por permissao antes de executar. | RF18, RF28 |
| E05-T12 | Preparar pontos de hook. | Eventos `pre_tool_use`, `post_tool_use` e `file_changed` ainda como interface. | RF31 |

## Criterios de aceite

* `/tools` lista as tools internas disponiveis.
* Tools internas nao acessam arquivos fora do workspace.
* Leitura e busca respeitam exclusoes, tamanho maximo e paths sensiveis.
* O resumo estrutural do projeto pode ser gerado e cacheado.
* Patches exibem diff antes de aplicar quando o modo exigir.
* Aplicacao de patch respeita permissoes e registra auditoria.

## Testes recomendados

* Registro e consulta de tools.
* Validacao de schema de entrada.
* Leitura de arquivo permitido, protegido, grande e inexistente.
* Busca com inclusoes e exclusoes.
* Cache de resumo estrutural.
* Diff e aplicacao de patch em diretorio temporario.

## Riscos

* Enviar contexto demais ao LLM por falta de filtros.
* Permitir alteracoes em paths protegidos por erro de normalizacao.
* Acoplar tools internas ao formato de prompt do LLM.

