import asyncio
import math
from pathlib import Path

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from src.agents import rag
from src.agents.rag import (
    LocalEmbedder,
    index_document,
    split_markdown,
    validate_vectors,
)
from src.db.models.knowledge import EMBEDDING_DIMENSIONS


def test_markdown_keeps_source_sections_and_bounds_chunks() -> None:
    document = "# Hero\n\n## Skill\n\n" + "description" * 50
    chunks = split_markdown(document, max_chars=80, chunk_overlap=0)
    assert len(chunks) > 1
    assert all(chunk.section == "Hero / Skill" for chunk in chunks)
    assert all(0 < len(chunk.content) <= 80 for chunk in chunks)
    assert "".join(chunk.content for chunk in chunks) == "description" * 50


def test_empty_document_has_no_chunks() -> None:
    assert split_markdown("# Title\n\n## Empty\n") == []


def test_complete_skill_is_not_cut_into_a_tiny_tail() -> None:
    description = "- 三技能·孤鹜断霞：" + "这是技能的完整说明。" * 20 + "手里没伞时只有击退效果。"
    chunks = split_markdown("# 公孙离介绍\n\n## 技能介绍\n\n" + description)
    assert len(chunks) == 1
    assert chunks[0].content == description
    assert chunks[0].section == "公孙离介绍 / 技能介绍"


def test_nested_headings_remain_in_source_metadata() -> None:
    chunks = split_markdown("# Hero\n\n## Skills\n\n### Defense\n\nBlock projectiles.")
    assert chunks[0].section == "Hero / Skills / Defense"


def test_token_budget_includes_headings_for_long_inputs() -> None:
    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "word": 1}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    document = "# Hero\n\n## Skills\n\n" + "word " * 1200
    chunks = split_markdown(document, tokenizer=tokenizer)
    assert len(chunks) > 1
    assert all(len(tokenizer.encode(f"{chunk.section}\n{chunk.content}").ids) <= 512 for chunk in chunks)


def test_embedding_failure_does_not_open_write_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag, "KNOWLEDGE_ROOT", tmp_path)
    source = tmp_path / "document.md"
    source.write_text("# Title\n\nA saved upload.", encoding="utf-8")

    class FailingEmbedder:
        tokenizer = None

        def passages(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("Model unavailable")

    class NoWriteFactory:
        def begin(self) -> None:
            pytest.fail("A failed embedding must not delete the old index")

    monkeypatch.setattr(rag, "session_factory", NoWriteFactory())
    with pytest.raises(RuntimeError, match="Model unavailable"):
        asyncio.run(index_document(source, FailingEmbedder()))


def test_missing_offline_model_directory_fails_without_downloading(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directory does not exist"):
        LocalEmbedder(tmp_path / "missing")


def test_vectors_require_matching_count_and_dimensions() -> None:
    vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    assert validate_vectors([vector], 1) == [vector]
    with pytest.raises(ValueError, match="count"):
        validate_vectors([], 1)
    with pytest.raises(ValueError, match="dimensions"):
        validate_vectors([[1.0, 2.0]], 1)


@pytest.mark.parametrize("value", [0.0, math.nan, math.inf])
def test_vectors_reject_zero_and_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite and nonzero"):
        validate_vectors([[value] * EMBEDDING_DIMENSIONS], 1)