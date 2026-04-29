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

A etapa 03 entrega a CLI interativa inicial: bootstrap do workspace local,
persistencia em `.onbot-cli`, loop continuo com `prompt_toolkit`, autocomplete
para slash commands, comandos internos minimos, renderizacao com Rich,
cancelamento local e registro de prompts/comandos no historico e na sessao.
