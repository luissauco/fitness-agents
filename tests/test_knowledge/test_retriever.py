"""Tests del KnowledgeRetriever sobre una colección poblada en `tmp_path`."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import Settings
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.retriever import KnowledgeRetriever, RetrievedChunk
from src.knowledge.sources import Reliability, SourceType, Topic
from tests.helpers import FakeEmbeddingManager, make_source


@pytest.fixture
def populated(
    settings: Settings, fake_embeddings: FakeEmbeddingManager, tmp_path: Path
) -> KnowledgeRetriever:
    """Indexa 3 documentos representativos y devuelve el retriever listo."""
    indexer = KnowledgeIndexer(settings, fake_embeddings)

    indexer.index_source(
        make_source(
            "training-doc",
            text="Hipertrofia volumen series efectivas entrenamiento. " * 30,
            file_path=tmp_path / "training.md",
            topics=[Topic.HYPERTROPHY, Topic.VOLUME],
            source_type=SourceType.GUIDELINE,
            reliability=Reliability.EXPERT_OPINION,
            author="Fran",
        )
    )
    indexer.index_source(
        make_source(
            "nutrition-doc",
            text="Macros proteína distribución dieta diaria. " * 30,
            file_path=tmp_path / "nutrition.md",
            topics=[Topic.NUTRITION, Topic.MACROS],
            source_type=SourceType.GUIDELINE,
            reliability=Reliability.EXPERT_OPINION,
            author="Fran",
        )
    )
    indexer.index_source(
        make_source(
            "study-doc",
            text="Meta-análisis sobre hipertrofia y entrenamiento de fuerza. " * 30,
            file_path=tmp_path / "study.md",
            topics=[Topic.HYPERTROPHY],
            source_type=SourceType.SCIENTIFIC_STUDY,
            reliability=Reliability.META_ANALYSIS,
            author="Schoenfeld",
            title="Schoenfeld 2017 meta",
        )
    )

    return KnowledgeRetriever(settings, fake_embeddings)


def test_retrieve_without_filters_returns_results(
    populated: KnowledgeRetriever,
) -> None:
    results = populated.retrieve("hipertrofia", k=10, score_threshold=0.0)
    assert len(results) > 0
    assert all(isinstance(r, RetrievedChunk) for r in results)
    assert all(0.0 <= r.score <= 1.0 for r in results)


def test_retrieve_respects_k(populated: KnowledgeRetriever) -> None:
    results = populated.retrieve("anything", k=2, score_threshold=0.0)
    assert len(results) <= 2


def test_filter_by_topic_isolates_nutrition_docs(
    populated: KnowledgeRetriever,
) -> None:
    results = populated.retrieve(
        "anything",
        topics=[Topic.NUTRITION],
        k=20,
        score_threshold=0.0,
    )
    assert results
    for chunk in results:
        assert Topic.NUTRITION in chunk.topics
        assert chunk.source_id == "nutrition-doc"


def test_filter_by_reliability_min_excludes_lower_tiers(
    populated: KnowledgeRetriever,
) -> None:
    results = populated.retrieve(
        "anything",
        reliability_min=Reliability.PEER_REVIEWED,
        k=20,
        score_threshold=0.0,
    )
    assert results
    for chunk in results:
        assert chunk.reliability.rank >= Reliability.PEER_REVIEWED.rank
    # Solo el documento Meta-analysis cumple el filtro.
    assert all(c.source_id == "study-doc" for c in results)


def test_filter_by_source_type(populated: KnowledgeRetriever) -> None:
    results = populated.retrieve(
        "anything",
        source_types=[SourceType.SCIENTIFIC_STUDY],
        k=20,
        score_threshold=0.0,
    )
    assert results
    for chunk in results:
        assert chunk.source_type == SourceType.SCIENTIFIC_STUDY


def test_filter_by_author(populated: KnowledgeRetriever) -> None:
    results = populated.retrieve(
        "anything",
        author="Schoenfeld",
        k=20,
        score_threshold=0.0,
    )
    assert results
    for chunk in results:
        assert chunk.author == "Schoenfeld"


def test_combined_filters_apply_with_and(
    populated: KnowledgeRetriever,
) -> None:
    """Con varios filtros se aplican todos (AND)."""
    results = populated.retrieve(
        "anything",
        topics=[Topic.HYPERTROPHY],
        reliability_min=Reliability.PEER_REVIEWED,
        k=20,
        score_threshold=0.0,
    )
    # Hypertrophy + meta-analysis ⇒ solo `study-doc`.
    assert results
    assert all(c.source_id == "study-doc" for c in results)


def test_retrieve_for_agent_training_excludes_nutrition_only_docs(
    populated: KnowledgeRetriever,
) -> None:
    context = populated.retrieve_for_agent("hipertrofia", agent_type="training", k=10)
    # `nutrition-doc` no tiene topics de training → no aparece su título en la salida.
    assert "nutrition-doc" not in context
    assert "training-doc" in context or "Schoenfeld 2017 meta" in context


def test_retrieve_for_agent_nutrition_excludes_training_only_docs(
    populated: KnowledgeRetriever,
) -> None:
    context = populated.retrieve_for_agent("macros", agent_type="nutrition", k=10)
    assert "training-doc" not in context
    assert "Schoenfeld 2017 meta" not in context  # solo HYPERTROPHY
    assert "nutrition-doc" in context


def test_retrieve_for_agent_progress_does_not_filter_topics(
    populated: KnowledgeRetriever,
) -> None:
    """`progress` no filtra topics ⇒ contexto cross-domain."""
    context = populated.retrieve_for_agent("ajuste plan", agent_type="progress", k=20)
    # Esperamos que aparezcan ambos dominios (al menos nutrición + entrenamiento).
    assert "nutrition-doc" in context
    assert "training-doc" in context or "Schoenfeld 2017 meta" in context


def test_retrieve_for_agent_invalid_type_raises(
    settings: Settings, fake_embeddings: FakeEmbeddingManager
) -> None:
    retriever = KnowledgeRetriever(settings, fake_embeddings)
    with pytest.raises(ValueError, match="agent_type"):
        retriever.retrieve_for_agent("query", agent_type="invalid")  # type: ignore[arg-type]


def test_format_context_with_empty_chunks_returns_placeholder() -> None:
    out = KnowledgeRetriever.format_context([])
    assert "Sin contexto" in out


def test_format_context_includes_required_fields(
    populated: KnowledgeRetriever,
) -> None:
    chunks = populated.retrieve("anything", k=2, score_threshold=0.0)
    text = KnowledgeRetriever.format_context(chunks)

    assert "---" in text
    assert "Fuente:" in text
    assert "Autor:" in text
    assert "Tipo:" in text
    assert "Fiabilidad:" in text
    # Algún título de los documentos sembrados aparece.
    assert any(
        title in text
        for title in ("training-doc", "nutrition-doc", "Schoenfeld 2017 meta")
    )


def test_score_threshold_filters_low_scores(
    populated: KnowledgeRetriever,
) -> None:
    """Con threshold = 1.0 ningún resultado pasa (score <= 1.0 estricto)."""
    results = populated.retrieve("anything", k=10, score_threshold=1.01)
    assert results == []
