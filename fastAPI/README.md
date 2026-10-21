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

Set `APP_OPENAI_API_KEY` as well. The application does not read `AI_KEY`.
Configure both values through the deployment environment and do not commit
credentials to `.env`.

The default OpenAI base URL is `https://api.openai.com/v1` and the default model
is `gpt-4o-mini`. Override them with `APP_OPENAI_BASE_URL` and `APP_OPENAI_MODEL`.
When the API key is missing or the upstream AI call fails, the stream emits an
ordinary `content` event containing `delta`, `question`, and a timestamped mock
`answer`, followed by `done` with the conversation ID. Mock answers are persisted
like normal answers. If the upstream stream already emitted partial content,
the mock text is appended to it and the combined answer is persisted.

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

## RAG 资料准备

第一版使用 `knowledge/` 中的 Markdown/TXT 作为共用测试知识库，暂不导入业务用户数据。

1. 阅读 [公孙离资料](knowledge/gongsunli.md)：内容来自用户，没有核实游戏版本；先把它当作检索样本，不当作官方攻略。
2. 保留文档标题与章节：后续按段落切片，并保存文件名、章节和片段顺序，便于回答时说明资料来源。当前尚未切片或生成向量。
3. 使用 [检查题](tests/fixtures/rag_questions.json)：`question` 是测试问题，`expected_answer` 是核对要点，不要求模型逐字复述。
4. 对 `answerable: true` 的题目，核对搜索片段是否包含答案，来源是否匹配 `source_sections`；该列表列出可接受的章节，多个章节可以提供相关证据。
5. 对 `answerable: false` 的题目，检查回答是否说明资料不足，而不是编造数值或最新版本结论。

检查题不是知识资料，不要把 `tests/` 导入知识库。当前聊天接口仍没有 RAG 检索，模拟回答也不能验证知识问答效果。
下一步先确认 PostgreSQL 的 `pgvector` 支持并选择可用的 Embedding 模型，再创建知识库表和入库脚本。

## Check

```bash
uv run ruff check src
uv run pytest
```
