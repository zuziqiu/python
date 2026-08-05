# Enterprise FastAPI Service

面向初学者的模块职责、调用链和核心原理说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## Setup

```bash
uv sync
cp .env.example .env
```

## PostgreSQL

Set `APP_DATABASE_URL` in `.env` for your local or managed PostgreSQL instance,
then apply the schema migration:

```bash
uv run alembic upgrade head
```

`APP_DATABASE_URL` is the only required production setting. Configure it with a
managed PostgreSQL connection string through the deployment environment; do not
commit production credentials to `.env`.

## Run

```bash
uv run uvicorn src.main:app --reload
```

API documentation: http://127.0.0.1:8000/docs

## Check

```bash
uv run ruff check src
uv run pytest
```
