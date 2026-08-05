# FastAPI 项目架构说明

## 1. 当前项目结构

```text
fastAPI/
├── .gitignore               # Git 忽略规则，应提交
├── .env.example              # 非敏感环境变量模板，应提交
├── .python-version          # 项目使用的 Python 版本
├── .venv/                   # uv 创建的隔离环境，不提交
├── .pytest_cache/           # pytest 测试框架的运行缓存，不提交
├── .ruff_cache/             # Ruff 代码检查工具的检查缓存，不提交
├── alembic.ini               # Alembic 数据库迁移配置
├── pyproject.toml           # 项目、依赖和工具配置
├── uv.lock                  # 精确锁定依赖版本
├── README.md                # 快速启动说明
├── ARCHITECTURE.md          # 当前架构说明
├── migrations/
│   ├── env.py                # Alembic 异步迁移运行环境
│   ├── script.py.mako        # 新迁移文件模板
│   └── versions/
│       └── 20260804_01_initial_chat_schema.py # 初始对话表迁移
├── src/
│   ├── __init__.py          # 将 src 标记为 Python 包
│   ├── __pycache__/         # Python 字节码缓存，不提交
│   ├── main.py              # 唯一应用入口和装配中心
│   ├── middleware.py        # 所有 HTTP 请求共用的处理逻辑
│   ├── api/
│   │   └── v1/
│   │       ├── __pycache__/ # Python 执行 API 模块生成的缓存，不提交
│   │       ├── router.py    # 聚合 v1 路由
│   │       ├── message.py   # POST /api/v1/message 接口
│   │       └── profile.py   # GET/POST /api/v1/profile 接口
│   ├── core/
│   │   ├── __pycache__/     # Python 执行 Core 模块生成的缓存，不提交
│   │   ├── config.py        # 配置读取与校验
│   │   ├── errors.py        # 通用业务异常基类
│   │   └── logging.py       # JSON 日志配置
│   ├── db/
│   │   ├── __init__.py      # 数据库基础设施包
│   │   ├── base.py          # SQLAlchemy ORM 模型基类
│   │   ├── session.py       # 异步连接池、事务会话与关闭逻辑
│   │   └── models/
│   │       ├── __init__.py  # 集中导入 ORM 模型，供迁移发现
│   │       ├── chat.py      # AI 对话会话和消息模型
│   │       ├── message.py   # message 表 ORM 模型
│   │       └── profile.py   # profile 表 ORM 模型
│   └── schemas/
│       ├── __pycache__/     # Python 执行 Schema 模块生成的缓存，不提交
│       ├── common.py        # 通用错误响应结构
│       ├── message.py       # message 接口请求和响应结构
│       └── profile.py       # profile 接口请求和响应结构
└── tests/
    ├── __pycache__/         # Python 执行测试生成的缓存，不提交
    └── test_api.py          # profile/message 接口行为测试
```

缓存目录属于磁盘上的真实结构，但不属于需要团队维护的源码结构。`__pycache__` 保存 Python 根据源码生成的 `.pyc` 字节码，用于加快导入；删除后会自动重建。

当前没有 `services/`、`repositories/` 或 `dependencies.py` 源码。数据层只负责连接池、事务会话和对话模型；只有接口开始有真实读写需求时，再增加对应的 Service 或 Repository，不提前创建空层。

## 2. 哪些内容提交 Git

Git 是版本控制工具，用于记录源码历史和团队协作。`.gitignore` 只忽略尚未跟踪的文件，不会删除磁盘文件，也不会自动移除已经提交过的文件。

| 内容                              | 是否提交 | 原因                            |
| --------------------------------- | -------- | ------------------------------- |
| `src/**/*.py`                     | 是       | 项目源码                        |
| `tests/**/*.py`                   | 是       | 测试代码                        |
| `pyproject.toml`                  | 是       | 依赖和工具配置                  |
| `uv.lock`                         | 是       | 锁定精确依赖版本                |
| `.python-version`                 | 是       | 统一 Python 版本                |
| `.gitignore`                      | 是       | 统一忽略规则                    |
| `.env.example`                    | 是       | 提供不含密钥的配置模板          |
| `alembic.ini`、`migrations/`      | 是       | 可重复、可审计的数据库结构变更  |
| `README.md`、`ARCHITECTURE.md`    | 是       | 项目文档                        |
| `.venv/`                          | 否       | 可由 `uv sync` 重建且与本机相关 |
| `__pycache__/`、`*.pyc`           | 否       | Python 自动生成的字节码缓存     |
| `.pytest_cache/`                  | 否       | pytest 自动生成的测试缓存       |
| `.ruff_cache/`                    | 否       | Ruff 自动生成的检查缓存         |
| `.env`、`.env.*`                  | 否       | 可能包含本地配置或密钥          |
| `build/`、`dist/`、`*.egg-info/`  | 否       | 可重新生成的构建产物            |
| `.DS_Store`、`.idea/`、`.vscode/` | 否       | 系统或个人编辑器配置            |

## 3. 根目录工具和文件

### `uv`

`uv` 是 Python 版本、虚拟环境和依赖管理工具：

- `uv sync` 根据 `pyproject.toml` 和 `uv.lock` 安装依赖。
- `uv run ...` 使用当前项目的 `.venv` 执行命令。
- `.venv/` 是隔离环境，防止不同项目的依赖互相冲突。

### `pyproject.toml`

作用类似 Node.js 的 `package.json`：

- `[project]` 保存项目名、版本、Python 要求和运行依赖。
- 运行依赖包含 FastAPI、SQLAlchemy、asyncpg、Alembic 和 greenlet。
- `[dependency-groups]` 保存 pytest、Ruff 等开发依赖。
- `[tool.uv] package = false` 表示这是直接运行的应用，不发布成 Python 库。
- `[tool.pytest.ini_options]` 保存测试配置。

### `pytest` 与 Ruff

- **pytest** 是测试框架，负责发现并运行 `tests/` 中的测试。
- **Ruff** 是 Python 代码检查工具，负责发现未使用导入、常见错误和不规范写法。

两者运行后产生的缓存可以删除，不提交 Git。

### `uv.lock`

记录依赖解析后的精确版本。团队执行 `uv sync` 时能安装相同版本，通常应提交且不手工编辑。

## 4. 应用入口与常规基础设施

### `src/main.py`

这是唯一应用入口。启动命令中的 `src.main:app` 表示：

1. 导入 `src/main.py`。
2. 获取其中的 `app` 对象。
3. 由 Uvicorn 运行这个 FastAPI 应用。

文件保留了常规项目需要的内容：

- `lifespan()`：应用启动时初始化日志，关闭时释放 SQLAlchemy 异步连接池。
- `create_app()`：创建 FastAPI 并注册中间件、路由和异常处理器。
- `handle_app_error()`：把可预期业务异常转换成统一 JSON。
- `handle_validation_error()`：把请求校验失败转换成统一 422 JSON。
- `app = create_app()`：创建最终运行的应用实例。

错误兜底不是额外业务接口，不会增加 API 路径；它只在请求发生错误时统一响应格式。

### `src/middleware.py`

中间件包裹每次 HTTP 请求，当前负责：

1. 接收或生成 `X-Request-ID`。
2. 计算请求耗时。
3. 把请求 ID 写回响应头。
4. 记录方法、路径、状态码和耗时。

这是适用于所有接口的常规基础设施，不是单独接口。

### `src/core/`

- `config.py`：用 `pydantic-settings` 读取并校验环境配置。
- `errors.py`：定义通用 `AppError`，供将来的业务错误使用。
- `logging.py`：把日志格式化为便于检索的 JSON。

## 5. PostgreSQL 与对话数据迁移

### 名词与设计目的

- **PostgreSQL**：保存应用长期数据的关系型数据库；这里保存 AI 对话会话和消息。
- **SQLAlchemy**：Python 操作数据库的工具。本项目用它把 Python 类映射为数据库表，这种方式叫 **ORM**（对象关系映射），避免在每个业务位置手写 SQL。
- **asyncpg**：SQLAlchemy 实际连接 PostgreSQL 时使用的异步驱动。异步表示等待数据库响应期间，服务可以处理其他请求。
- **连接池**：预先维护一批可复用的数据库连接。请求不必每次新建 TCP 连接，减少延迟和数据库压力。
- **事务**：一组数据库操作要么全部成功并提交，要么在异常时全部回滚，避免只保存了半段对话历史。
- **外键**：数据库级关联约束。`chat_messages.conversation_id` 必须指向真实会话；删除会话时关联消息会一并删除。
- **索引**：为常用查询列建立的数据结构。消息按 `conversation_id` 查询时可避免扫描整张消息表。
- **Alembic**：SQLAlchemy 的数据库迁移工具，用 Python 文件记录“数据库结构从一个版本变到下一个版本”的步骤。
- **迁移（migration）**：一次可提交、可审查、可按顺序执行的结构变更，例如创建表、增加列或增加索引。

为什么需要 `migrations/`：Python ORM 模型只描述“代码期望的表结构”，不能可靠地更新已经存在的生产数据库。迁移文件把每次结构变化纳入 Git 历史，使开发、测试和生产环境都能按同一顺序升级，并可追踪当前数据库处于哪个版本。应用启动时不自动改表，部署流程显式执行迁移，避免服务进程在运行时意外修改生产数据结构。

### 数据库连接

`src/core/config.py` 从环境变量读取 `APP_DATABASE_URL` 和连接池参数；本地默认值指向 `localhost:5432`。生产环境应由部署平台注入连接串，`.env` 只能保存本地配置，绝不提交。

`src/db/session.py` 是唯一创建 SQLAlchemy 异步引擎的位置：

1. 使用 `asyncpg` 连接 PostgreSQL。
2. 通过连接池复用连接，并用 `pool_pre_ping` 淘汰失效连接。
3. `get_db_session()` 为一次业务操作提供事务：成功提交，发生异常回滚。
4. 应用关闭时由 `close_database()` 释放连接池资源。

目前接口尚未写入数据库，因此应用只在使用会话时才实际连接 PostgreSQL；这使不依赖数据库的接口和测试仍可运行。

### 对话数据模型

初始迁移建立以下最小结构：

```text
chat_conversations
  id, title, created_at

chat_messages
  id, conversation_id, role, content, created_at
```

- 每个 `chat_messages` 通过 `conversation_id` 从属于一个会话；删除会话时，数据库级外键会删除对应消息。
- `role` 只能是 `user`、`assistant` 或 `system`，由数据库约束保护历史消息格式。
- 消息按 `created_at` 顺序读取，供后续的 AI 对话接口组装上下文。

### 本地数据库与迁移

设置 `.env` 中的 `APP_DATABASE_URL`，然后执行：

```bash
uv run alembic upgrade head
```

`alembic.ini` 是 Alembic 的入口配置，告诉它迁移目录在哪里；`migrations/env.py` 负责加载本项目数据库配置和 ORM 模型；`migrations/versions/` 存放按时间顺序执行的迁移文件；`script.py.mako` 是生成新迁移文件时使用的模板。Alembic 不应在 FastAPI 应用启动时自动运行；生产环境应在部署流程中显式执行 `alembic upgrade head`。

## 6. 当前业务接口

### 路由注册过程

```text
src/api/v1/message.py, src/api/v1/profile.py
  -> src/api/v1/router.py 聚合
  -> src/main.py 以 /api/v1 前缀注册
  -> POST /api/v1/message, GET/POST /api/v1/profile
```

`src/api/v1/message.py` 使用 FastAPI 装饰器声明 message 接口：

```python
@router.post("/message", response_model=MessageResponse)
async def receive_message(payload: MessageRequest) -> MessageResponse:
    ...
```

请求 JSON：

```json
{
  "user_id": "user-1",
  "text": "Hello FastAPI"
}
```

响应 JSON：

```json
{
  "user_id": "user-1",
  "text": "Hello FastAPI"
}
```

`src/api/v1/profile.py` 提供 profile 名称更新接口：

```python
@router.post("/profile", response_model=ProfileResponse)
async def update_profile_name(payload: ProfileUpdateRequest) -> ProfileResponse:
    ...
```

`src/schemas/message.py` 和 `src/schemas/profile.py` 中的 Pydantic 模型负责校验请求并约束响应。接口只接收 JSON；form-data 会得到 422 校验错误。

### 为什么保留 `api/v1`

`v1` 表示第一个公开 API 版本。以后出现不兼容修改时，可以增加 `v2`，让旧客户端有迁移时间。

保留版本号的好处：

1. 新旧契约可以暂时并存。
2. 不强迫所有客户端同时升级。
3. 从 URL 能看出使用的契约版本。

代价是增加目录层级。当前项目虽然只有一个接口，但用户已经询问过版本设计，因此保留 `v1`；它不会额外创建接口。

## 7. 一次请求如何流动

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant Middleware as 中间件
    participant FastAPI as FastAPI/Pydantic
    participant Route as message 路由

    Client->>Middleware: POST /api/v1/message + JSON
    Middleware->>Middleware: 生成 request_id，开始计时
    Middleware->>FastAPI: 转交请求
    FastAPI->>FastAPI: 校验 MessageRequest
    FastAPI->>Route: receive_message(payload)
    Route-->>FastAPI: MessageResponse
    FastAPI->>FastAPI: 按 response_model 序列化
    FastAPI-->>Middleware: HTTP 200
    Middleware->>Middleware: 添加响应头并记录耗时
    Middleware-->>Client: JSON + X-Request-ID
```

校验发生在路由函数执行之前。JSON 不合法时，路由不会执行，而是由统一校验错误处理器返回 422。

## 8. FastAPI 核心概念

- **`APIRouter`**：拆分和聚合路由。
- **`response_model`**：约束响应结构，并用于生成 OpenAPI 文档。
- **Pydantic**：根据 Python 类型注解校验请求和序列化响应。
- **OpenAPI**：描述 API 路径、参数和响应的标准格式。
- **Swagger UI**：根据 OpenAPI 生成的可交互接口页面。
- **ASGI**：Python Web 服务器调用异步 Web 应用的标准接口。
- **Uvicorn**：监听端口并通过 ASGI 调用 FastAPI 的 Web 服务器。

## 9. 进程、线程与 Uvicorn

### 通俗理解

- **进程**像一间独立办公室，有自己的内存和资源。
- **线程**像同一办公室里的员工，共享办公室里的内存和资源。

不同进程默认不共享内存；同一进程的线程共享内存，所以线程同时修改数据时需要小心。

### 专业总结

进程是操作系统进行资源分配和隔离的基本单位；线程是进程内部执行任务的基本单位。Python 的 `async def` 主要通过事件循环在等待 I/O 时切换任务，不等同于自动创建线程，也不等同于 CPU 并行计算。

### `--reload` 如何工作

```bash
uv run uvicorn src.main:app --reload
```

执行这一条命令后，Uvicorn 自动创建：

1. 监控父进程：观察 Python 文件是否变化。
2. 服务子进程：加载 FastAPI 并处理请求。

保存源码后，父进程停止旧子进程并创建新子进程，新代码因此生效。正常停止时在启动终端按 `Ctrl+C`，让父子进程一起退出。

不需要热重载时：

```bash
uv run uvicorn src.main:app
```

生产环境需要多个独立 worker 时可以明确指定：

```bash
uv run uvicorn src.main:app --workers 4
```

`--reload` 用于开发，`--workers` 用于多进程运行，不同时使用。每个 worker 都有自己的内存和全局变量。

## 10. 扩展原则

现在已经具备 PostgreSQL 数据层和 AI 对话的会话/消息模型，但还没有具体的对话接口或模型供应商调用。后续按真实需求增加对应层：

- 路由开始包含复杂业务规则时，增加 Service。
- 多个接口需要复用查询或持久化逻辑时，增加 Repository。
- 多处需要复用会话或鉴权上下文时，增加依赖注入模块。
- 不为了看起来“企业级”而提前创建空模块或示例接口。

## 11. 常用命令

```bash
# 安装或同步依赖
uv sync

# 启动开发服务
uv run uvicorn src.main:app --reload

# 运行测试
uv run pytest

# 检查代码
uv run ruff check src migrations tests

# 应用数据库迁移
uv run alembic upgrade head
```

启动后可访问：

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>
