"""Index saved Markdown files and search them with a local embedding model."""

# argparse 是 Python 标准库，用来解析 ingest/search 等命令行参数。
import argparse

# asyncio 是 Python 标准库，负责异步执行索引、检索和资源清理流程。
import asyncio

# hashlib 是 Python 标准库，用来计算原始文档的 SHA-256 内容指纹。
import hashlib

# json 是 Python 标准库，用来把命令结果格式化输出为 JSON。
import json

# math 是 Python 标准库，用来检查向量中的数字是否有效且有限。
import math

# collections.abc 提供 Iterable 类型，标注可逐项读取的向量集合。
from collections.abc import Iterable

# dataclasses 提供 dataclass 装饰器，用于定义轻量的数据对象。
from dataclasses import dataclass

# pathlib 提供跨平台路径操作；Path 用于查找文档和模型文件。
from pathlib import Path

# huggingface_hub 用于从 Hugging Face 模型仓库取得 tokenizer 文件。
from huggingface_hub import hf_hub_download

# langchain_text_splitters 提供 Markdown 标题识别和递归文本切片工具。
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

# sqlalchemy 提供 ORM 数据库操作、查询构造及执行 SQL 的工具。
from sqlalchemy import delete, insert, select, text

# tokenizers 提供模型 tokenizer，用于按模型实际规则计算输入 token 数。
from tokenizers import Tokenizer

# src.db.models.knowledge 是项目的知识分块数据库模型模块，提供表模型及向量配置。
from src.db.models.knowledge import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    KnowledgeChunk,
)

# src.db.session 是项目的数据库会话模块，提供数据库引擎和异步会话工厂。
from src.db.session import engine, session_factory

# 项目里的知识文档目录；入库时只接受这个目录中的文件。
KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"


@dataclass(frozen=True)
class DocumentChunk:
    """切分后的一段文字及其所属章节标题。"""

    # 章节路径（例如“英雄介绍 / 技能”），检索结果可用它说明内容出处。
    section: str
    # 实际送去生成向量、并最终存入数据库的文本片段。
    content: str


def split_markdown(
    document: str, max_chars: int = 400, chunk_overlap: int = 60,
    tokenizer: Tokenizer | None = None,
) -> list[DocumentChunk]:
    """按 Markdown 章节和长度拆分文档，保留每段所属的标题路径。"""
    # 避免无效切分设置导致无法切分，或片段重叠长度大于片段本身。
    if max_chars < 1 or not 0 <= chunk_overlap < max_chars:
        raise ValueError("Require positive chunk size and overlap smaller than chunk size")
    # 先按 Markdown 的一级到六级标题归组，这样每段正文都能关联到章节标题。
    sections = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#" * level, f"h{level}") for level in range(1, 7)],
        return_each_line=True,
    ).split_text(document)
    chunks: list[DocumentChunk] = []

    def measure(value: str) -> int:
        # 真正入库时用模型 tokenizer 计 token；单元测试可不加载模型而按字符计数。
        return len(tokenizer.encode(value, add_special_tokens=False).ids) if tokenizer else len(value)

    for section in sections:
        # 把各级标题串成完整路径，作为片段的来源上下文。
        heading = " / ".join(section.metadata[f"h{level}"] for level in range(1, 7) if f"h{level}" in section.metadata)
        if len(heading) > 512:
            raise ValueError("Document heading exceeds 512 characters")
        # 模型输入最多 512 token，预留标题及分隔符空间后再决定正文可用长度。
        budget = min(max_chars, 508 - measure(heading)) if tokenizer else max_chars
        if budget < 1:
            raise ValueError("Document heading leaves no token budget for content")
        # 优先在段落、换行和中文标点处分段，尽量避免把语义完整的句子切开。
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=budget,
            chunk_overlap=min(chunk_overlap, budget // 5),
            length_function=measure,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            keep_separator="end",
        )
        for content in splitter.split_text(section.page_content):
            # 最后再检查“标题 + 正文”的真实 token 数，超限就报错而非静默截断。
            if tokenizer and len(tokenizer.encode(f"{heading}\n{content}").ids) > 512:
                raise ValueError("Chunk exceeds the model's 512-token input limit")
            chunks.append(DocumentChunk(heading, content))
    return chunks


def validate_vectors(vectors: Iterable[Iterable[float]], count: int) -> list[list[float]]:
    # 将模型输出统一转换成普通 float 列表，以匹配数据库向量字段的输入格式。
    result = [[float(value) for value in vector] for vector in vectors]
    # 每个文本必须恰好对应一个向量，否则文本和向量会错位。
    if len(result) != count:
        raise ValueError("Embedding count does not match input count")
    for vector in result:
        # 所有向量必须与所选模型的维度一致，且不能包含无穷/非数字或全零值。
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding dimensions")
        if not all(math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError("Embedding must be finite and nonzero")
    return result


class LocalEmbedder:
    def __init__(self, model_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding

        # 指定本地模型目录时要求目录已存在，并让模型只从本地读取，避免意外联网下载。
        if model_dir is not None and not model_dir.is_dir():
            raise ValueError("Offline model directory does not exist")
        # 加载本地嵌入模型；模型会把文字转换成可计算语义相似度的数字向量。
        self.model = TextEmbedding(
            model_name=EMBEDDING_MODEL,
            cache_dir=str(Path.home() / ".cache" / "enterprise-api" / "embeddings"),
            threads=2,
            specific_model_path=str(model_dir.resolve()) if model_dir is not None else None,
            local_files_only=model_dir is not None,
        )
        # tokenizer 用来按模型实际的 token 规则检查输入长度，而不是估算字符数。
        tokenizer_path = (
            model_dir / "tokenizer.json" if model_dir is not None
            else Path(hf_hub_download(
                repo_id="Qdrant/bge-small-zh-v1.5", filename="tokenizer.json",
                cache_dir=str(Path.home() / ".cache" / "enterprise-api" / "embeddings"),
                local_files_only=True,
            ))
        )
        # 从 tokenizer.json 读取模型对应的分词规则；之后用它统计文本实际占用的 token 数。
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        # 关闭超长文本自动截断；程序会在 passages() 中检查长度并明确报错，避免丢失内容。
        self.tokenizer.no_truncation()
        # 关闭自动补齐；这里逐条检查文本长度，不需要为了组成批次而给短文本添加填充 token。
        self.tokenizer.no_padding()

    def passages(self, texts: list[str]) -> list[list[float]]:
        # 文档片段超过模型输入限制时直接失败，避免生成被截断、内容不完整的向量。
        if any(len(self.tokenizer.encode(value).ids) > 512 for value in texts):
            raise ValueError("Embedding input exceeds 512 tokens; split it before embedding")
        # passage_embed 专用于待检索的资料正文；同时核对返回向量数量和格式。
        return validate_vectors(self.model.passage_embed(texts), len(texts))

    def query(self, question: str) -> list[float]:
        # 查询文本不能为空；query_embed 按模型对“搜索问题”的方式生成一个向量。
        if not question.strip():
            raise ValueError("Question must not be empty")
        return validate_vectors(self.model.query_embed(question), 1)[0]


async def index_document(path: Path, embedder: LocalEmbedder) -> dict[str, object]:
    """读取一份已保存的 Markdown 文档，生成向量并原子替换其索引。"""
    # 规范化路径，并把数据库 source 保存为相对知识目录的路径。
    path = path.resolve()
    source = path.relative_to(KNOWLEDGE_ROOT.resolve()).as_posix()
    # 当前索引器只处理 Markdown，并检查来源路径能放进数据库字段。
    if path.suffix.lower() != ".md":
        raise ValueError("This first importer accepts Markdown files only")
    if len(source) > 512:
        raise ValueError("Source path exceeds 512 characters")
    # 读取原始文件字节；utf-8-sig 同时兼容带 UTF-8 BOM 的文件。
    raw = path.read_bytes()
    chunks = split_markdown(raw.decode("utf-8-sig"), tokenizer=embedder.tokenizer)
    if not chunks:
        raise ValueError("Document has no indexable content")
    # 把“章节标题 + 片段正文”一起向量化，让检索也能利用章节上下文。
    # 模型计算较耗时，放入线程执行，避免阻塞 asyncio 的事件循环。
    vectors = await asyncio.to_thread(
        embedder.passages, [f"{chunk.section}\n{chunk.content}" for chunk in chunks]
    )
    # 对原始文件计算 SHA-256，记录此索引对应的文档版本，便于识别内容变化。
    source_hash = hashlib.sha256(raw).hexdigest()
    # 为每个片段组装一行数据库数据；position 记录它在原文中的顺序。
    rows = [
        {
            "source": source,
            "position": position,
            "section": chunk.section,
            "content": chunk.content,
            "source_hash": source_hash,
            "embedding_model": EMBEDDING_MODEL,
            "embedding": vector,
        }
        for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    # 一个事务内先删除同一来源的旧片段，再写入新片段；失败时旧索引不会被部分替换。
    async with session_factory.begin() as db:
        # 同一文档若被并发索引，使用数据库锁让它们依次完成，避免互相覆盖。
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:source, 0))"),
            {"source": source},
        )
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source == source))
        await db.execute(insert(KnowledgeChunk), rows)
    # 返回本次入库摘要，不返回完整向量（向量通常很长）。
    return {
        "status": "ready",
        "source": source,
        "source_hash": source_hash,
        "model": EMBEDDING_MODEL,
        "chunks": len(chunks),
        "dimensions": EMBEDDING_DIMENSIONS,
        "first_vector_preview": vectors[0][:8],
    }


async def search_knowledge(
    question: str, embedder: LocalEmbedder, limit: int = 3,
) -> list[dict[str, object]]:
    # 限制返回条数，防止调用方请求过多结果。
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    # 把问题也转成向量；同一向量空间里的资料向量才能做语义相似度比较。
    vector = await asyncio.to_thread(embedder.query, question)
    # cosine_distance 计算问题向量与每个资料向量之间的余弦距离，越小表示越相似。
    distance = KnowledgeChunk.embedding.cosine_distance(vector).label("distance")
    # 只搜索当前嵌入模型生成的向量，按距离从近到远取最相关的 limit 个片段。
    statement = (
        select(
            KnowledgeChunk.source, KnowledgeChunk.position,
            KnowledgeChunk.section, KnowledgeChunk.content, distance,
        )
        .where(KnowledgeChunk.embedding_model == EMBEDDING_MODEL)
        .order_by(distance, KnowledgeChunk.source, KnowledgeChunk.position)
        .limit(limit)
    )
    # 执行查询并将每条数据库记录转成字典，供后续调用方读取。
    async with session_factory() as db:
        results = (await db.execute(statement)).mappings().all()
    return [dict(row) for row in results]


async def run_command(args: argparse.Namespace) -> None:
    try:
        # 模型初始化可能耗时，因此放在线程中；ingest 和 search 共用同一模型实例。
        embedder = await asyncio.to_thread(LocalEmbedder, args.model_dir)
        if args.command == "ingest":
            result = await index_document(args.path, embedder)
        else:
            result = await search_knowledge(args.question, embedder, args.limit)
        # 将索引摘要或检索片段以格式化 JSON 输出到终端。
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        # 无论命令成功还是失败，都释放数据库连接池。
        await engine.dispose()


def main() -> None:
    # 创建命令行参数解析器；description 使用文件开头的说明，显示在 --help 帮助信息中。
    parser = argparse.ArgumentParser(description=__doc__)
    # 可选的离线模型目录；type=Path 会把用户输入的路径字符串转换成 Path 对象。
    # 例如：python -m src.agents.rag --model-dir /models/bge ingest knowledge/doc.md
    parser.add_argument("--model-dir", type=Path, help="Use an existing FastEmbed ONNX model directory offline")
    # 注册子命令，并把用户选的命令保存到 args.command；required=True 表示必须选一个子命令。
    # 本程序支持 ingest（建立索引）和 search（搜索片段）。
    commands = parser.add_subparsers(dest="command", required=True)
    # 定义 ingest 子命令；用户执行 ingest 时，会显示此帮助说明。
    ingest = commands.add_parser("ingest", help="Index a fully saved Markdown upload")
    # ingest 必须接收一个文档路径；type=Path 将其转换为 Path 供后续读取文件。
    ingest.add_argument("path", type=Path)
    # 定义 search 子命令，用于查找相似资料片段，而不是生成最终回答。
    search = commands.add_parser("search", help="Return matching passages, not generated answers")
    # search 必须接收要查询的问题文本。
    search.add_argument("question")
    # 可选的结果数量；若用户不传 --limit，则默认返回最相似的 3 个片段。
    search.add_argument("--limit", type=int, default=3)
    # 读取并校验终端参数，得到 args；再启动 asyncio 事件循环运行异步命令处理函数。
    asyncio.run(run_command(parser.parse_args()))


if __name__ == "__main__":
    # 只有直接用 python -m src.agents.rag 运行本文件时才启动命令行；
    # 被其他模块导入时不会意外执行命令。
    main()