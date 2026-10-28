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

The default AI provider is Copilot. Set `APP_AI_PROVIDER=openai` and
`APP_OPENAI_API_KEY` to use the previous OpenAI path instead. The application
does not read `AI_KEY`. Do not commit credentials to `.env`.

The default OpenAI base URL is `https://api.openai.com/v1` and the default model
is `gpt-4o-mini`. Override them with `APP_OPENAI_BASE_URL` and `APP_OPENAI_MODEL`.
In OpenAI mode only, when the API key is missing or the upstream AI call fails, the stream emits an
ordinary `content` event containing `delta`, `question`, and a timestamped mock
`answer`, followed by `done` with the conversation ID. Mock answers are persisted
like normal answers. If the upstream stream already emitted partial content,
the mock text is appended to it and the combined answer is persisted.

## Run

```bash
uv run uvicorn src.main:app --reload
```

API documentation: http://127.0.0.1:8000/docs

## 项目启动后自动进行 Copilot 企业认证

启动命令不变：`uv run uvicorn src.main:app --reload`。
默认 `APP_AI_PROVIDER=copilot`，通过官方 Python SDK 调用 Copilot。
不需要 GitHub MCP 或 OpenAI API key。数据库仍按原生命周期要求连接。

先按 [官方指南](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
安装一次官方 CLI；macOS 可以执行：

```bash
brew install --cask copilot-cli
```

之后只需要原项目启动命令：

1. FastAPI 启动后在后台检查独立 SDK 登录状态，不阻塞服务接收请求。
2. 未登录时自动运行官方 `copilot login`，由 CLI 发起浏览器授权；选择获得企业席位的账号。
   若当前环境选择设备码流程，请按服务终端显示的地址和验证码完成授权。
3. 登录完成后重新加载 SDK 运行时并验证认证状态，聊天接口直接调用 Copilot。
4. 登录配置与 SDK 共用 `~/.cache/enterprise-api/copilot/`，
   由官方 CLI 管理凭据。普通的 `copilot login` 默认目录与此目录不同；
   项目不读取 VS Code Token，也不把 Token 返回给前端。
   SDK 使用支持本机钥匙串登录的 `copilot-cli` 模式；不能改为 `empty` 模式，
   后者会禁用系统钥匙串读取，导致 CLI 已登录而 SDK 仍显示未认证。
5. 已保存的有效登录会自动复用；本机多个进程通过文件锁串行化登录，并在取得锁后重新检查认证。
   热重载会停止本进程正在等待的登录子进程；尚未完成的授权可能需要重新进行。

可访问 `GET /api/v1/copilot/status` 查看 `starting`、`login_required`、
`authenticating`、`ready` 或 `failed` 状态及稳定错误码。`ready` 仅证明认证可用，
不保证模型权限或额度；真实聊天仍可能报告上游错误。
未认证时聊天接口返回 HTTP 503；模型调用失败时输出 SSE `error`，
不输出 `done`、不保存失败轮次，也不退回模拟回答。
缺少 CLI 时服务保留可访问状态，并在日志中明确提示安装步骤。
启动检查上限 30 秒，等待本机登录锁及授权合计上限 300 秒。
取消或超时后需重启服务重试；不会后台无限反复弹出授权。

配置项：

| 配置 | 默认值 | 用途 |
|---|---|---|
| `APP_AI_PROVIDER` | `copilot` | 切到 `openai` 可保留原聊天行为 |
| `APP_COPILOT_AUTO_LOGIN` | `true` | 本机未登录时自动发起官方授权 |
| `APP_COPILOT_CLI_PATH` | 空 | 自动从 PATH 查找，也可指定官方 CLI 绝对路径 |
| `APP_COPILOT_RUNTIME_PATH` | 空 | 默认使用 CLI；可指定独立官方运行时 |
| `APP_COPILOT_MODEL` | `auto` | 选择企业允许的模型 |

聊天每个 HTTP 请求使用独立 SDK 会话，并显式传递历史消息；在空临时工作目录运行，
禁用工具、MCP、技能、本地配置发现、文件 hooks 及 Git 操作，不读取项目业务文件。
单轮模型请求等待上限 300 秒，客户端断开时取消任务并中止会话。
这是本机单用户开发功能（登录锁使用 Unix `flock`），不是生产、多租户或共享企业席位方案。
部署时应关闭自动登录并按企业策略配置凭据。不要将本机开发服务公开到网络。

`uv run --module src.AIModels.copilot` 仍是可选诊断入口，而不是项目启动命令。
它使用相同认证目录，不自动登录；只有模型真实返回预期结果才输出 `COPILOT_OK`。
企业账号须允许 CLI，模型请求可能消耗账户额度。

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
