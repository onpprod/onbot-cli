# Especificacao de Requisitos de Software (SRS)

## Sistema: onbot-cli

---

# 1. Introducao

## 1.1 Proposito

Este documento descreve os requisitos funcionais e nao funcionais do
**onbot-cli**, uma CLI interativa agentica para desenvolvimento de software.

O objetivo do sistema e ajudar o usuario a criar, modificar, documentar,
depurar, validar e explicar codigo dentro de um projeto local, mantendo o
usuario no controle das decisoes criticas.

O documento serve como base para:

* desenvolvimento do sistema;
* validacao de requisitos;
* definicao de escopo;
* alinhamento tecnico;
* avaliacao de aceite.

---

## 1.2 Escopo

O **onbot-cli** e uma ferramenta CLI interativa que:

* opera exclusivamente em modo interativo;
* utiliza modelos de linguagem (LLMs);
* entende e manipula projetos locais;
* auxilia em workflows de criacao de codigo;
* le, cria e altera arquivos;
* executa comandos locais de forma controlada;
* integra-se com Git;
* permite tools Python criadas pelo usuario;
* permite hooks e comandos customizados;
* mantem historico, logs, cache e configuracao em diretorio local.

Nao faz parte do escopo inicial:

* modo batch;
* modo daemon;
* uso via pipe;
* execucao autonoma sem interacao;
* interface grafica.

A ferramenta atua como um **agente assistido**, no qual o usuario permanece
responsavel por aprovar, revisar ou configurar a autonomia das acoes.

---

## 1.3 Definicoes

| Termo | Definicao |
| --- | --- |
| Workspace | Diretorio onde o `onbot-cli` e iniciado. |
| Sessao | Execucao interativa do `onbot-cli`. |
| Tool | Abstracao de acao que o agente pode invocar. |
| Tool interna | Tool implementada pelo proprio `onbot-cli` e sujeita as politicas internas de seguranca. |
| Tool Python local | Tool implementada pelo usuario como codigo Python carregavel. E considerada codigo confiavel do usuario. |
| Manifesto de tool | Metadados usados para registrar nome, descricao, entradas e risco de uma tool. |
| Hook | Acao configurada pelo usuario para rodar em eventos do ciclo de vida do agente. |
| Comando customizado | Comando slash definido pelo usuario como prompt/template reutilizavel. |
| Modo de execucao | Politica ativa que define o nivel de autonomia do agente. |
| Permissao | Regra `allow`, `ask` ou `deny` aplicada a tools, comandos, paths ou operacoes. |
| Interacao pendente | Estado registrado quando o agente aguarda confirmacao, escolha ou continuidade do usuario antes de retomar um workflow. |
| LLM | Modelo de linguagem. |
| Patch | Alteracao proposta em arquivos. |
| Sandbox logico | Restricao aplicada pelo `onbot-cli` as suas tools internas para manter operacoes dentro do workspace. |
| Workflow agentico | Sequencia orientada a objetivo, como criar feature, documentar, depurar ou refatorar. |

---

# 2. Visao Geral do Sistema

## 2.1 Perspectiva

O sistema consiste em:

```text
Usuario
  |
  v
Interface CLI Interativa
  |
  v
Controlador do Agente
  |
  +--> Workflows de codigo
  +--> Modelo LLM
  +--> Sistema de permissoes
  +--> Tools internas
  +--> Tools Python locais
  +--> Hooks
  +--> Git
  |
  v
Workspace local + .onbot-cli
```

---

## 2.2 Restricoes fundamentais

* O sistema deve operar exclusivamente em modo interativo.
* O diretorio atual deve ser tratado como workspace principal.
* Tools internas devem respeitar o sandbox logico do workspace.
* Operacoes sensiveis devem seguir o modo de execucao e as regras de permissao.
* Tools Python locais e hooks definidos pelo usuario sao considerados codigo
  confiavel do usuario e nao devem ser sandboxados pelo `onbot-cli`.
* Acoes relevantes devem ser registradas para auditoria local.

---

# 3. Requisitos Funcionais

## RF01 - Inicializacao do sistema

O sistema deve iniciar em modo interativo:

```bash
onbot-cli
```

O diretorio atual deve ser definido como workspace.

---

## RF02 - Estrutura local

O sistema deve criar automaticamente:

```text
.onbot-cli/
```

Estrutura minima:

```text
.onbot-cli/
  config.yaml
  sessions/
  history/
  logs/
  cache/
  tools/
  hooks/
  commands/
```

---

## RF03 - Modo interativo

O sistema deve manter sessao continua com comandos internos:

```text
/help
/exit
/clear
/status
/config
/tools
/permissions
/mode
/git
/hooks
/commands
/history
```

O sistema nao deve exigir suporte inicial a execucao nao interativa.

---

## RF04 - Comunicacao com LLM

O sistema deve suportar provedores OpenAI-compatible.

Deve permitir configurar:

* `base_url`;
* `api_key` ou variavel de ambiente;
* `model`;
* parametros de geracao.

---

## RF05 - Streaming de resposta

Respostas do modelo devem ser exibidas em streaming.

---

## RF06 - Historico de sessao

Cada sessao deve ser persistida em:

```text
.onbot-cli/sessions/
```

---

## RF07 - Restricao ao workspace para tools internas

Tools internas de filesystem, patch, busca e comandos devem impedir acesso fora
do workspace, salvo quando uma futura configuracao explicita permitir
diretorios adicionais.

Essa restricao nao se aplica ao codigo interno de tools Python locais ou hooks
criados pelo usuario.

---

## RF08 - Leitura de arquivos

O agente deve ler arquivos respeitando:

* limites de tamanho;
* exclusoes;
* arquivos sensiveis;
* regras de permissao;
* modo de execucao ativo.

---

## RF09 - Listagem e busca

O sistema deve permitir:

* listagem de arquivos;
* busca textual;
* busca por padroes de arquivos;
* identificacao de arquivos relevantes para uma tarefa.

---

## RF10 - Planejamento

O sistema deve gerar planos de execucao antes de acoes relevantes.

Planos devem conter:

* objetivo;
* arquivos ou areas provaveis;
* passos propostos;
* riscos;
* validacoes esperadas;
* criterio de conclusao.

---

## RF11 - Proposta de alteracao

O agente deve propor alteracoes via diff ou resumo estruturado antes da
aplicacao quando o modo de execucao exigir revisao.

---

## RF12 - Aplicacao de patch

Alteracoes em arquivos devem respeitar:

* modo de execucao;
* regras `allow`, `ask` e `deny`;
* paths protegidos;
* registro de auditoria.

---

## RF13 - Criacao de arquivos

Criacao de arquivos deve respeitar modo de execucao, regras de permissao e
paths protegidos.

---

## RF14 - Execucao segura de comandos

O sistema deve permitir execucao de comandos locais de forma controlada,
incluindo comandos de teste, lint, formatacao, build e diagnostico.

---

## RF15 - Classificacao de risco

Comandos e tools devem ser classificados como:

```text
SAFE
CAUTION
DANGEROUS
BLOCKED
```

---

## RF16 - Politica de comandos

O sistema deve:

* bloquear comandos proibidos;
* exigir confirmacao quando o modo ou regras determinarem;
* alertar o usuario para riscos;
* registrar comando, decisao, saida e codigo de saida;
* proteger paths sensiveis.

---

## RF17 - Validacao de caminhos

Todos os caminhos usados por tools internas devem:

* pertencer ao workspace;
* ser normalizados;
* nao permitir traversal;
* tratar symlinks de forma segura.

---

## RF18 - Aprovacao do usuario

O sistema deve solicitar confirmacao para:

* alteracoes em arquivos quando exigido;
* execucao de comandos quando exigido;
* operacoes Git destrutivas ou remotas;
* invocacao de tools ou hooks quando exigido;
* acoes potencialmente perigosas.

---

## RF19 - Registro de acoes

O sistema deve registrar:

* prompts;
* respostas;
* chamadas de tools;
* comandos;
* decisoes de permissao;
* alteracoes;
* operacoes Git;
* hooks executados;
* resultados.

---

## RF20 - Configuracao local

Configuracao do projeto deve ser mantida em:

```text
.onbot-cli/config.yaml
```

---

## RF21 - Configuracao global

O sistema deve usar configuracao global apenas para:

* provedores;
* modelos;
* endpoints;
* preferencias padrao nao sensiveis.

Dados de projeto, sessao, auditoria e cache devem permanecer no workspace.

---

## RF22 - Resumo do projeto

O sistema deve gerar resumo estrutural do projeto, incluindo:

* arvore relevante;
* linguagens detectadas;
* dependencias principais;
* comandos provaveis de teste, lint, formatacao e build;
* arquivos de configuracao importantes;
* convencoes detectadas.

---

## RF23 - Limite de execucao

O agente deve ter limite maximo de passos configuravel.

---

## RF24 - Cancelamento

Execucao deve poder ser interrompida via terminal.

---

## RF25 - Catalogo de tools

O sistema deve manter um catalogo de tools disponiveis para o agente.

O catalogo deve permitir:

* listar tools disponiveis via `/tools`;
* exibir nome, descricao, entradas esperadas e classificacao de risco;
* habilitar ou desabilitar tools por configuracao;
* diferenciar tools internas de tools Python locais.

---

## RF26 - Adicao de tools Python locais

O sistema deve permitir adicionar tools implementadas em Python de forma simples.

Cada tool Python local deve declarar:

* nome unico;
* descricao;
* esquema de entrada;
* classificacao de risco padrao;
* funcao ou classe de execucao.

Tools Python locais devem ser tratadas como codigo confiavel do usuario:

* nao devem ser sandboxadas pelo `onbot-cli`;
* nao devem ter acesso a filesystem, subprocessos ou rede bloqueado pelo
  `onbot-cli`;
* podem usar APIs auxiliares do `ToolContext`, mas nao sao obrigadas a se
  limitar a elas;
* devem ser carregadas apenas de paths configurados;
* devem ter invocacoes registradas em auditoria;
* sao responsabilidade do usuario que as criou, instalou ou habilitou.

---

## RF27 - Integracao com Git

O sistema deve tratar Git como capacidade central.

Deve suportar, no minimo:

* detectar repositorio Git;
* consultar status;
* consultar diff;
* consultar arquivos alterados;
* criar branch;
* preparar mensagens de commit;
* executar commit mediante permissao;
* exibir resumo das mudancas;
* proteger operacoes destrutivas, como reset, clean, rebase, force push e
  remocao de branches.

Operacoes remotas, destrutivas ou irreversiveis devem exigir confirmacao
explicita.

---

## RF28 - Sistema de permissoes

O sistema deve suportar regras de permissao declarativas.

Tipos de regra:

```text
allow
ask
deny
```

Regras devem poder ser aplicadas a:

* tools;
* comandos shell;
* operacoes de arquivo;
* paths;
* operacoes Git;
* hooks;
* tools Python locais.

Ordem de precedencia:

```text
deny > ask > allow > modo de execucao
```

O comando `/permissions` deve permitir consultar e alterar permissoes durante a
sessao.

---

## RF29 - Modos de execucao

O sistema deve suportar modos de execucao interativos.

Modos iniciais:

| Modo | Comportamento |
| --- | --- |
| `plan` | Permite leitura, busca, resumo, Git status/diff e planejamento. Bloqueia escrita e comandos mutaveis. |
| `default` | Permite leitura. Solicita confirmacao para escrita, comandos, Git mutavel, hooks e tools de risco. |
| `accept_edits` | Permite leitura e edicoes no workspace sem prompt, exceto paths protegidos. Comandos e Git mutavel continuam sujeitos a permissao. |
| `trusted` | Reduz prompts para acoes nao bloqueadas. Deve continuar respeitando regras `deny` e paths protegidos de tools internas. |
| `locked` | Executa apenas acoes explicitamente permitidas por regras `allow`; demais acoes sao negadas. |

O comando `/mode` deve permitir consultar e alterar o modo ativo.

---

## RF30 - Workflows agenticos de criacao de codigo

O sistema deve oferecer suporte a workflows de desenvolvimento comuns usando
etapas basicas reutilizaveis.

Etapas basicas:

* entender objetivo;
* inspecionar projeto;
* criar ou revisar requisitos;
* criar ou revisar arquitetura;
* planejar tasks;
* implementar feature;
* refatorar feature;
* depurar erro;
* criar ou atualizar testes;
* rodar testes;
* rodar lint, formatacao ou build;
* validar resultado;
* revisar diff;
* atualizar documentacao;
* explicar mudancas.

Workflows minimos:

* desenvolvimento de feature;
* correcao de bug;
* refatoracao;
* criacao de documentacao;
* revisao de codigo;
* preparacao de commit.

---

## RF31 - Hooks

O sistema deve permitir hooks configurados pelo usuario.

Eventos minimos:

* `session_start`;
* `user_prompt_submit`;
* `pre_tool_use`;
* `post_tool_use`;
* `permission_request`;
* `file_changed`;
* `git_operation`;
* `session_end`.

Hooks devem poder:

* executar script ou comando local;
* receber payload estruturado;
* registrar resultado;
* injetar contexto quando aplicavel;
* permitir, negar ou pedir confirmacao em eventos de permissao quando
  aplicavel.

Hooks definidos pelo usuario sao codigo confiavel do usuario e nao devem ser
sandboxados pelo `onbot-cli`.

---

## RF32 - Comandos customizados

O sistema deve permitir comandos slash customizados definidos pelo usuario.

Comandos customizados devem:

* ficar em `.onbot-cli/commands/`;
* ser definidos como arquivos Markdown ou YAML;
* aparecer em `/commands` e no autocomplete;
* aceitar argumentos;
* expandir para prompts ou workflows reutilizaveis;
* poder chamar etapas basicas de workflow.

Exemplos:

```text
/feature
/docs
/review
/fix-bug
/prepare-commit
```

---

## RF33 - Continuidade conversacional e confirmacoes pendentes

O sistema deve diferenciar uma nova tarefa de uma resposta a uma interacao
pendente.

Quando o agente solicitar confirmacao, escolha ou continuidade, o sistema deve:

* registrar uma interacao pendente com identificador unico;
* persistir o workflow, etapa atual, payload relevante e opcoes aceitas;
* interpretar respostas curtas como `sim`, `nao`, `continuar`, `cancelar` ou
  escolhas numericas como decisao da pendencia ativa;
* retomar, cancelar ou ajustar o workflow pendente conforme a decisao;
* limpar a pendencia apos conclusao, cancelamento, erro ou expiracao;
* registrar pergunta, resposta e decisao em sessao e auditoria;
* incluir historico recente e estado pendente no contexto do proximo turno de
  forma limitada e com redacao de segredos.
* aplicar acoes estruturadas de arquivo, como criar, editar, mover e excluir,
  somente depois de confirmacao e avaliacao de permissao.

Se nao houver interacao pendente ativa, respostas curtas como `sim` ou `nao` nao
devem ser interpretadas automaticamente como objetivo amplo para novo workflow.
O sistema deve pedir esclarecimento ou tratar a entrada como prompt comum de
forma explicita.

Confirmacoes para acoes mutaveis, como escrita, patch, comando shell, Git, hook
ou tool de risco, devem passar por `ApprovalService` e `PermissionManager`. Uma
pergunta gerada em texto livre pelo LLM nao deve conceder permissao nem substituir
uma aprovacao estruturada.

Para alteracoes de arquivo, o LLM deve produzir uma acao estruturada separada da
resposta textual. O sistema deve materializar a alteracao apenas por servicos
internos controlados, como `PatchService`, `PathGuard` e avaliacao de permissao.

---

# 4. Workflows Ideais

## 4.1 Desenvolvimento de feature

```text
1. Entender objetivo do usuario.
2. Inspecionar estrutura e convencoes do projeto.
3. Criar ou atualizar requisitos quando necessario.
4. Criar ou atualizar arquitetura quando necessario.
5. Planejar tasks pequenas e verificaveis.
6. Implementar a feature.
7. Refatorar a implementacao quando houver ganho claro.
8. Criar ou atualizar testes.
9. Rodar testes e comandos de validacao.
10. Depurar falhas.
11. Revisar diff e impacto.
12. Explicar mudancas e proximos passos.
```

---

## 4.2 Criacao de documentacao

```text
1. Identificar publico e objetivo da documentacao.
2. Inspecionar requisitos, arquitetura e codigo relevante.
3. Planejar estrutura do documento.
4. Redigir conteudo.
5. Validar consistencia com o codigo.
6. Atualizar links, indices ou referencias.
7. Revisar clareza e completude.
8. Explicar mudancas.
```

---

## 4.3 Correcao de bug

```text
1. Entender sintoma, erro ou comportamento esperado.
2. Reproduzir ou localizar evidencias.
3. Investigar causa raiz.
4. Planejar correcao minima.
5. Implementar correcao.
6. Criar ou atualizar teste de regressao.
7. Rodar validacoes.
8. Explicar causa e solucao.
```

---

## 4.4 Refatoracao

```text
1. Definir escopo e objetivo tecnico.
2. Verificar baseline com testes ou validacoes existentes.
3. Planejar passos pequenos.
4. Aplicar mudancas preservando comportamento.
5. Rodar testes frequentemente.
6. Revisar diff para evitar alteracoes funcionais acidentais.
7. Explicar resultado e riscos residuais.
```

---

## 4.5 Preparacao de commit

```text
1. Consultar Git status e diff.
2. Agrupar mudancas relacionadas.
3. Rodar validacoes apropriadas.
4. Preparar mensagem de commit.
5. Solicitar confirmacao do usuario.
6. Criar commit se aprovado.
7. Exibir resumo final.
```

---

# 5. Requisitos Nao Funcionais

## RNF01 - Linguagem

O sistema deve ser desenvolvido em Python.

---

## RNF02 - Interface

Deve utilizar:

```text
Typer
Rich
prompt_toolkit
```

---

## RNF03 - Compatibilidade

Suporte minimo:

* Windows;
* Linux.

---

## RNF04 - Seguranca

O sistema deve ser seguro por padrao para suas tools internas.

Tools Python locais e hooks do usuario sao uma fronteira de confianca separada:
o sistema deve deixar claro que esse codigo roda sob responsabilidade do
usuario.

---

## RNF05 - Observabilidade

Logs devem ser registrados localmente.

---

## RNF06 - Modularidade

O sistema deve ser modular.

---

## RNF07 - Extensibilidade

Deve permitir adicao de novas tools Python sem alteracao do nucleo do agente.

A adicao deve exigir apenas:

* criar um modulo Python seguindo o contrato de tool;
* registrar a tool por manifesto, decorador ou configuracao;
* reiniciar ou recarregar o catalogo de tools.

---

## RNF08 - Performance

Deve evitar leitura excessiva de arquivos.

---

## RNF09 - Controle de contexto

Deve limitar dados enviados ao modelo.

---

## RNF10 - Testabilidade

Deve permitir testes automatizados.

---

## RNF11 - Privacidade

Nao deve expor dados sensiveis ao LLM sem necessidade ou permissao.

---

## RNF12 - Auditabilidade

Todas acoes relevantes devem ser rastreaveis.

---

## RNF13 - Persistencia local

Todos os dados de projeto do `onbot-cli` devem estar em `.onbot-cli`.

---

## RNF14 - Experiencia do usuario

A interface deve ser fluida, responsiva e adequada a iteracao de desenvolvimento
de codigo.

---

# 6. Regras de Seguranca

## 6.1 Sandbox de diretorio para tools internas

Tools internas nao devem sair do workspace.

Essa garantia nao se aplica a tools Python locais nem hooks criados pelo
usuario, pois esses itens sao tratados como codigo confiavel.

---

## 6.2 Paths protegidos

Escritas em paths protegidos devem exigir confirmacao ou ser bloqueadas conforme
modo e regras:

```text
.git/
.onbot-cli/config.yaml
.onbot-cli/logs/
.idea/
.vscode/
.env
*.pem
*.key
```

---

## 6.3 Comandos proibidos

Exemplos:

```text
rm -rf /
format
shutdown
reboot
```

---

## 6.4 Execucao controlada

Comandos executados por tools internas devem:

* ser exibidos;
* ser classificados;
* ser validados;
* seguir modo de execucao;
* seguir regras de permissao;
* ser registrados.

---

# 7. Estrutura de Dados

## Sessao

```json
{
  "timestamp": "",
  "messages": [],
  "actions": [],
  "tool_calls": [],
  "commands": [],
  "git_operations": [],
  "permission_decisions": [],
  "hooks": [],
  "pending_interactions": []
}
```

---

## Configuracao

```yaml
model:
  base_url: ""
  api_key_env: "OPENAI_API_KEY"
  model: ""

agent:
  max_steps: 20

workspace:
  max_file_size_kb: 256

permissions:
  mode: "default"
  allow: []
  ask: []
  deny: []
  protected_paths:
    - ".git/"
    - ".env"

git:
  enabled: true
  require_confirmation_for_remote: true
  require_confirmation_for_destructive: true

tools:
  enabled: []
  disabled: []
  paths:
    - ".onbot-cli/tools"

hooks:
  enabled: true
  paths:
    - ".onbot-cli/hooks"

commands:
  paths:
    - ".onbot-cli/commands"
```

---

## Manifesto de tool

```yaml
name: ""
description: ""
risk: "SAFE"
module: ""
callable: ""
input_schema: {}
trusted: true
```

---

## Hook

```yaml
name: ""
event: "pre_tool_use"
command: ""
enabled: true
```

---

## Comando customizado

```yaml
name: "feature"
description: "Planeja e implementa uma feature."
arguments:
  - name: "descricao"
    required: true
prompt: ""
workflow: "feature_development"
```

---

# 8. Requisitos Futuros

* Interface TUI (Textual)
* RAG local
* Plugins externos
* Suporte a multiplos agentes
* Integracao com provedores externos de tarefas

---

# 9. Criterios de Aceite

O sistema sera considerado valido quando:

* iniciar corretamente em modo interativo;
* criar e usar `.onbot-cli`;
* respeitar isolamento de diretorio para tools internas;
* executar comandos com seguranca;
* permitir leitura e alteracao controlada de arquivos;
* manter historico de sessoes;
* integrar com LLM configurado;
* listar tools disponiveis;
* permitir adicao simples de tools Python locais confiaveis;
* integrar com Git;
* suportar regras de permissao;
* suportar modos `plan`, `default`, `accept_edits`, `trusted` e `locked`;
* retomar ou cancelar workflows a partir de confirmacoes pendentes sem tratar
  `sim` ou `nao` como nova conversa acidental;
* suportar hooks;
* suportar comandos customizados;
* apoiar workflows de feature, bugfix, refatoracao, documentacao e commit;
* bloquear comandos proibidos;
* exigir confirmacao para acoes criticas conforme modo e regras.

---

# Conclusao

Este documento define o **onbot-cli** como uma CLI agentica interativa para
criacao de codigo, com workflows de desenvolvimento, Git, tools extensiveis,
hooks, comandos customizados, controle de permissoes e execucao supervisionada.
