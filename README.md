# onbot-cli

CLI interativa agentica para desenvolvimento de software local.

## Desenvolvimento

Requisitos:

* Python 3.14+
* Poetry 2.3+

Instale as dependencias:

```powershell
poetry install
```

Execute a CLI em desenvolvimento:

```powershell
poetry run onbot-cli
```

Rode os testes:

```powershell
poetry run pytest
```

## Estado atual

A etapa 02 entrega a persistencia local inicial: criacao idempotente de
`.onbot-cli`, configuracao local com defaults, leitura opcional de configuracao
global nao sensivel, sessoes, historico de comandos, auditoria com redacao
basica de segredos e cache estrutural do projeto.
