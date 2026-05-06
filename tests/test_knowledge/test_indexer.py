"""Tests del KnowledgeIndexer.

Usa una colección ChromaDB persistente real apuntando a `tmp_path`, y un
embedding manager ficticio para no descargar modelos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import Settings
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.sources import (
    KnowledgeRegistry,
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)
from tests.helpers import FakeEmbeddingManager, make_source


def test_index_source_creates_chunks(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    source = make_source(
        "src-1",
        text="Texto largo de prueba. " * 200,
        file_path=tmp_path / "src-1.md",
    )

    n = indexer.index_source(source)

    assert n > 0
    stats = indexer.get_stats()
    assert stats["total_chunks"] == n
    assert stats["unique_sources"] == 1
    assert "src-1" in stats["source_ids"]


def test_reindex_is_idempotent(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    source = make_source(
        "src-2",
        text="Mismo texto cada vez. " * 200,
        file_path=tmp_path / "src-2.md",
    )

    n1 = indexer.index_source(source)
    n2 = indexer.index_source(source)

    assert n1 == n2
    assert indexer.get_stats()["total_chunks"] == n1


def test_reindex_with_smaller_text_drops_orphans(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    """Re-indexar con texto más corto NO debe dejar huérfanos del indexado anterior."""
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    md_path = tmp_path / "src-3.md"

    long_source = make_source(
        "src-3",
        text="Texto largo. " * 500,
        file_path=md_path,
    )
    n_long = indexer.index_source(long_source)

    short_source = make_source(
        "src-3",
        text="Texto corto.",
        file_path=md_path,
    )
    n_short = indexer.index_source(short_source)

    assert n_short < n_long
    assert indexer.get_stats()["total_chunks"] == n_short


def test_delete_removes_only_target_source(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    a = make_source("src-a", text="Aaa " * 200, file_path=tmp_path / "a.md")
    b = make_source("src-b", text="Bbb " * 200, file_path=tmp_path / "b.md")
    n_a = indexer.index_source(a)
    n_b = indexer.index_source(b)

    deleted = indexer.delete_source("src-a")

    assert deleted == n_a
    stats = indexer.get_stats()
    assert stats["total_chunks"] == n_b
    assert "src-a" not in stats["source_ids"]
    assert "src-b" in stats["source_ids"]


def test_delete_nonexistent_source_is_noop(
    settings: Settings, fake_embeddings: FakeEmbeddingManager
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    assert indexer.delete_source("ghost-source") == 0


def test_index_all_uses_registry(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)

    a = make_source("src-a", text="A " * 200, file_path=tmp_path / "a.md")
    b = make_source("src-b", text="B " * 200, file_path=tmp_path / "b.md")

    registry_path = tmp_path / "registry.json"
    registry = KnowledgeRegistry(registry_path)
    registry.add(a)
    registry.add(b)
    registry.save()

    result = indexer.index_all(registry_path)

    assert result["sources_processed"] == 2
    assert result["sources_failed"] == 0
    assert result["total_chunks"] > 0


def test_index_all_reports_failures_without_aborting(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    """Si una fuente apunta a un archivo inexistente, el resto se procesa igualmente."""
    indexer = KnowledgeIndexer(settings, fake_embeddings)

    good = make_source("good", text="Contenido. " * 100, file_path=tmp_path / "good.md")
    ghost = KnowledgeSource(
        id="ghost",
        title="Ghost",
        author="X",
        source_type=SourceType.GUIDELINE,
        topics=[Topic.HYPERTROPHY],
        reliability=Reliability.EXPERT_OPINION,
        file_path=str(tmp_path / "no-such-file.md"),
    )

    registry_path = tmp_path / "registry.json"
    registry = KnowledgeRegistry(registry_path)
    registry.add(good)
    registry.add(ghost)
    registry.save()

    result = indexer.index_all(registry_path)

    assert result["sources_processed"] == 1
    assert result["sources_failed"] == 1
    assert result["total_chunks"] > 0
    assert result["errors"][0]["source_id"] == "ghost"


def test_missing_file_raises(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    ghost = KnowledgeSource(
        id="ghost",
        title="Ghost",
        author="X",
        source_type=SourceType.GUIDELINE,
        topics=[Topic.HYPERTROPHY],
        reliability=Reliability.EXPERT_OPINION,
        file_path=str(tmp_path / "no-such-file.md"),
    )
    with pytest.raises(FileNotFoundError):
        indexer.index_source(ghost)


def test_metadata_includes_inherited_fields(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> None:
    indexer = KnowledgeIndexer(settings, fake_embeddings)
    source = make_source(
        "src-meta",
        text="Texto. " * 200,
        file_path=tmp_path / "meta.md",
        topics=[Topic.HYPERTROPHY, Topic.VOLUME],
        reliability=Reliability.PEER_REVIEWED,
        author="Schoenfeld",
        title="Paper de prueba",
    )
    indexer.index_source(source)

    payload = indexer.collection.get(include=["metadatas"])
    metadatas = payload["metadatas"] or []
    assert metadatas

    sample = metadatas[0]
    assert sample["source_id"] == "src-meta"
    assert sample["author"] == "Schoenfeld"
    assert sample["title"] == "Paper de prueba"
    assert sample["reliability"] == Reliability.PEER_REVIEWED.value
    assert sample["reliability_rank"] == Reliability.PEER_REVIEWED.rank
    # Boolean flags por topic.
    assert sample.get("t_hypertrophy") is True
    assert sample.get("t_volume") is True
    # Topic no presente: o falta la clave o es False.
    assert not sample.get("t_nutrition", False)
