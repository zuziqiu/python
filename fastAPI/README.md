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

Set `APP_SILICONFLOW_API_KEY` as well. The application does not read `AI_KEY`.
Configure both values through the deployment environment and do not commit
credentials to `.env`.

## Run

```bash
uv run uvicorn src.main:app --reload
```

API documentation: http://127.0.0.1:8000/docs

## Conversation API

`POST /api/v1/conversation` accepts JSON and returns `text/event-stream`:

```json
{
  "user_id": "01",
  "conversation_id": null,
  "messages": [
    { "role": "user", "content": "Previous question" },
    { "role": "assistant", "content": "Previous answer" }
  ],
  "content": "Current question"
}
```

`conversation_id` may be omitted for the first turn. The stream emits
`reasoning`, `content`, and `done` events. Reasoning is never persisted; after a
complete model response, the current user message and final assistant answer are
appended to `conversation.messages` in one database transaction.

## Check

```bash
uv run ruff check src
uv run pytest
```
