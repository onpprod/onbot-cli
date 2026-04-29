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

A etapa 05 entrega o nucleo seguro de tools internas: catalogo `/tools`,
contratos de tool, listagem, leitura, busca textual, resumo estrutural com
cache, selecao de contexto, aplicacao controlada de patches, auditoria,
permissoes e interfaces iniciais para hooks.
