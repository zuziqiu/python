# Enterprise FastAPI Service

面向初学者的模块职责、调用链和核心原理说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## Setup

```bash
uv sync
```

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
