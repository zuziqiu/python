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
2. 保留文档标题与章节：入库时按段落切片，并保存文件名、章节和片段顺序，便于回答时说明资料来源。
3. 使用 [检查题](tests/fixtures/rag_questions.json)：`question` 是测试问题，`expected_answer` 是核对要点，不要求模型逐字复述。
4. 对 `answerable: true` 的题目，核对搜索片段是否包含答案，来源是否匹配 `source_sections`；该列表列出可接受的章节，多个章节可以提供相关证据。
5. 对 `answerable: false` 的题目，检查回答是否说明资料不足，而不是编造数值或最新版本结论。

检查题不是知识资料，不要把 `tests/` 导入知识库。当前聊天接口仍没有 RAG 检索，模拟回答也不能验证知识问答效果。

### PostgreSQL 向量扩展

本机已确认 Postgres.app 的 PostgreSQL 18 附带 `pgvector 0.8.6`，但扩展需要在每个使用它的数据库中单独启用。
首次安装扩展需要数据库管理员，不要为此给项目账号 `app` 超级管理员权限。
在本机 Postgres.app 的默认管理员设置下，用当前 macOS 用户执行一次：

```bash
/Applications/Postgres.app/Contents/Versions/latest/bin/psql -X -w -h localhost -d enterprise_api -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
uv run alembic upgrade head
```

第一条让数据库支持向量类型与距离计算；第二条记录迁移版本，重复执行不会重复安装扩展。
若其他电脑提示权限不足，应由数据库管理员执行第一条。回退此扩展迁移同样需要扩展所有者权限，且存在向量字段依赖时不会强制删除数据。

可在 pgAdmin 的 Query Tool 中验证：

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector AS cosine_distance;
```

第二条应返回 `0`，表示两个相同向量的余弦距离为零。这只是数据库运算检查，还不是文本语义搜索。

### 管理员上传后的转换与入库

当前用 `knowledge/gongsunli.md` 模拟管理员已经保存完成的上传文件，不新增上传接口。
已选择本地中文模型 `BAAI/bge-small-zh-v1.5`，通过 FastEmbed/ONNX Runtime 在 CPU 上生成 512 维向量，无需 OpenAI 密钥。
首次运行需要从官方 Hugging Face 下载模型，模型权重约 90 MB，缓存于 `~/.cache/enterprise-api/embeddings/`。
下载失败不会改用随机向量或模拟成功。

上传后的处理时机是：文件完整保存成功后执行索引任务；不要在上传到一半时执行，也不要每次提问都重新索引文档。
生产场景可以放进持久化任务队列，由 worker 调用 `src.agents.rag.index_document`；本练习先手动执行同一处理逻辑：

```bash
uv sync
uv run alembic upgrade head
uv run --module src.agents.rag ingest knowledge/gongsunli.md
```

命令按顺序完成：读取 UTF-8 文档、调用 `langchain-text-splitters` 切片、本地生成向量、校验数量和维度、保存到 `knowledge_chunk`。
切分配置在 `src/agents/rag.py` 的 `split_markdown()`，不再使用原来的 200 字符硬切逻辑：

- `MarkdownHeaderTextSplitter` 按 Markdown 的 1 到 6 级标题整理内容，并保留完整标题路径。
- `RecursiveCharacterTextSplitter` 优先沿段落、换行和中文标点递归拆分；末级才允许逐字符拆分超长内容。
- 实际入库以 BGE 模型自带 tokenizer 计数，正文目标上限为 400 token、重叠上限为 60 token；短章节不会为了凑长度被强行拆分。
- 标题也计入模型输入预算，逐片验证“标题 + 正文”不超过 512 token；发现超长输入会报错，不允许静默截断后入库。
- 单独调用 `split_markdown()` 不传 tokenizer 时按字符计数，主要用于不加载模型的快速测试；真实入库会传入 tokenizer。

这里的标题切分组件不是完整的 Markdown AST 解析器，复杂表格、图片及扫描 PDF 还需要额外解析流程。
生成向量成功之后才打开数据库写事务；同一来源的旧片段替换和新片段写入一起提交。
重复入库会替换同一来源，不会无限追加副本。生成向量或数据库写入失败时，旧索引保留；需重新执行命令重试。
没有单独的上传任务状态表，当前命令只有事务提交成功后才打印 `status: ready`。

验证检索：

```bash
uv run --module src.agents.rag search "公孙离怎么挡飞行物？" --limit 3
```

该命令只将问题转换成向量并返回数据库中距离最近的原文、来源和章节，不调用聊天模型，也不保证每个问题都有答案。
小型样本使用精确距离排序，暂不建近似向量索引。当前聊天接口还没有接入此检索，仍保留之前的模拟回答行为。

可在 pgAdmin 查看真实存储情况：

```sql
SELECT source, position, section, embedding_model,
       vector_dims(embedding) AS dimensions
FROM knowledge_chunk
ORDER BY source, position;
```

如官方网络不可用，可以使用从官方来源取得的完整 FastEmbed ONNX 模型目录（含 `model_optimized.onnx`、配置及 tokenizer 文件），禁止只提供原始 PyTorch 权重：

```bash
uv run --module src.agents.rag --model-dir /path/to/model ingest knowledge/gongsunli.md
uv run --module src.agents.rag --model-dir /path/to/model search "公孙离怎么挡飞行物？"
```

2026-10-21 实际验证：网络恢复后已从官方 Hugging Face 下载模型，未使用第三方镜像。
已删除原来手写硬切生成的 6 条公孙离向量记录，并确认删除后为 0 条。
使用 LangChain 切分器重新转换后，`gongsunli.md` 已生成并保存 5 个真实片段向量，每个向量为 512 维。
技能章节完整保留，没有原来独立的“退效果。”尾片段。
检索“公孙离怎么挡飞行物？”时，第一条命中“实战思路”（余弦距离约 0.306），第二条命中完整的“技能介绍”。
此结果仅证明样本文档的向量生成、入库和检索可运行，不代表完整问答效果达标；聊天 API 还没有接入检索结果。

## Check

```bash
uv run ruff check src
uv run pytest
```
