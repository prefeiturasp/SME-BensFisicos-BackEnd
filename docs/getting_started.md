# Getting Started

Fluxo atual para executar e validar o projeto localmente via Docker Compose.

## Requisitos

- Docker + plugin Docker Compose
- Arquivo `.env` na raiz (ver `.env.example`)

## Preparação

```bash
cp .env.example .env
docker compose -f docker-compose-dev.yml up --build
```

Serviços (`docker-compose-dev.yml`): `db` (Postgres 15 + healthcheck), `web` (Django via `Dockerfile.dev`, porta `8000`).

## Banco e acesso inicial

```bash
make init-db                # migrate + cria superusuário (defaults embutidos no Makefile)
make setup-grupos-permissoes
make seed-base              # massa de demonstração (opcional)
```

## Acessos locais

- Admin: `http://localhost:8000/admin/`
- Schema OpenAPI: `http://localhost:8000/api/schema/`
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`

## Notas

- Não há versionamento `/api/v1/` (mantido sem versionar, sem quebrar o frontend).
- Sem endpoint de verificação de saúde na API. Só o banco tem healthcheck no Compose.
- `Makefile` com alvos de qualidade (`test`, `lint`, `typecheck`, `coverage`, `schema`, `docs`); ver `make help`. As ferramentas (`pytest`, `black`, `ruff`, `mypy`, `sphinx`) entram no item `requirements/`.
