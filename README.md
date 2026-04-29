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

A etapa 01 entrega a fundacao do projeto: empacotamento, dependencias base,
ponto de entrada `onbot-cli`, estrutura modular inicial, bootstrap minimo,
contratos compartilhados e testes unitarios basicos.
