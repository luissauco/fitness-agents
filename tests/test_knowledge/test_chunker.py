"""Tests del chunker."""

from __future__ import annotations

import pytest

from src.config.settings import Settings
from src.knowledge.chunker import Chunker
from src.knowledge.sources import (
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)


def _build_source(source_type: SourceType = SourceType.GUIDELINE) -> KnowledgeSource:
    return KnowledgeSource(
        id="test-source",
        title="Test Source",
        author="Test Author",
        source_type=source_type,
        topics=[Topic.HYPERTROPHY, Topic.VOLUME],
        reliability=Reliability.EXPERT_OPINION,
        file_path="not-used.md",
    )


def test_chunking_respects_size(settings: Settings) -> None:
    """Cada chunk debe acercarse a CHUNK_SIZE pero no superarlo de forma significativa."""
    chunker = Chunker(settings)
    text: str = "Hola mundo. " * 200  # ~2400 chars
    chunks = chunker.chunk(text, _build_source())

    assert len(chunks) > 1, "Texto largo debe producir múltiples chunks."
    # Permitimos cierta holgura por separadores conservados.
    max_allowed = settings.CHUNK_SIZE * 1.3
    for chunk in chunks:
        assert len(chunk.content) <= max_allowed, (
            f"Chunk de {len(chunk.content)} chars excede {max_allowed:.0f}."
        )


def test_overlap_increases_total_length(settings: Settings) -> None:
    """Con overlap > 0, la suma de longitudes de chunks supera la del texto original."""
    text: str = "ab cd ef gh ij " * 200  # ~3000 chars

    s_no_overlap = Settings(
        ANTHROPIC_API_KEY="x",
        CHUNK_SIZE=200,
        CHUNK_OVERLAP=0,
        CHROMA_PERSIST_DIR=settings.CHROMA_PERSIST_DIR,
    )
    s_with_overlap = Settings(
        ANTHROPIC_API_KEY="x",
        CHUNK_SIZE=200,
        CHUNK_OVERLAP=80,
        CHROMA_PERSIST_DIR=settings.CHROMA_PERSIST_DIR,
    )

    chunks_no = Chunker(s_no_overlap).chunk(text, _build_source())
    chunks_yes = Chunker(s_with_overlap).chunk(text, _build_source())

    total_no = sum(len(c.content) for c in chunks_no)
    total_yes = sum(len(c.content) for c in chunks_yes)
    assert total_yes > total_no, "Overlap > 0 debería incrementar el material total."


def test_metadata_propagated_to_each_chunk(settings: Settings) -> None:
    chunker = Chunker(settings)
    source = _build_source()
    chunks = chunker.chunk("texto cualquiera. " * 100, source)

    assert chunks
    for i, chunk in enumerate(chunks):
        assert chunk.source_id == source.id
        assert chunk.author == source.author
        assert chunk.source_type == source.source_type
        assert chunk.reliability == source.reliability
        assert chunk.topics == source.topics
        assert chunk.chunk_index == i


def test_preprocess_removes_timestamps(settings: Settings) -> None:
    chunker = Chunker(settings)
    text: str = "[00:12] Inicio. [01:23:45] Medio. (00:05) Final."
    cleaned = chunker.preprocess(text, SourceType.VIDEO_TRANSCRIPT)
    assert "[00:12]" not in cleaned
    assert "[01:23:45]" not in cleaned
    assert "(00:05)" not in cleaned
    # Las palabras "útiles" sobreviven.
    assert "Inicio" in cleaned
    assert "Final" in cleaned


def test_preprocess_removes_noise_markers(settings: Settings) -> None:
    chunker = Chunker(settings)
    text: str = "Hola [música] mundo [risas] y (aplausos) fin. [Music] [LAUGHTER]"
    cleaned = chunker.preprocess(text, SourceType.VIDEO_TRANSCRIPT)
    assert "música" not in cleaned.lower()
    assert "risas" not in cleaned.lower()
    assert "aplausos" not in cleaned.lower()
    assert "music" not in cleaned.lower() or "Music" not in cleaned  # caso markers
    assert "Hola" in cleaned
    assert "fin" in cleaned


def test_preprocess_does_not_strip_timestamps_outside_video(
    settings: Settings,
) -> None:
    """Una guideline puede mencionar `[00:12]` legítimamente; no debe limpiarse."""
    chunker = Chunker(settings)
    text: str = "Ejercicio a [00:12] de la sesión."
    cleaned = chunker.preprocess(text, SourceType.GUIDELINE)
    assert "[00:12]" in cleaned


def test_transcript_separators_break_at_questions(settings: Settings) -> None:
    chunker = Chunker(settings)
    text: str = (
        "## Pregunta 1\n"
        + "Texto largo para asegurar split. " * 30
        + "\n## Pregunta 2\n"
        + "Texto largo segunda parte. " * 30
    )
    chunks = chunker.chunk(text, _build_source(SourceType.VIDEO_TRANSCRIPT))

    contents = [c.content for c in chunks]
    full = " ".join(contents)
    assert "Pregunta 1" in full
    assert "Pregunta 2" in full

    # Existe al menos un chunk donde solo aparece una de las dos preguntas
    # → los separadores específicos sí están haciendo su trabajo.
    has_separated = any(
        ("Pregunta 1" in c) ^ ("Pregunta 2" in c) for c in contents
    )
    assert has_separated, "El chunker no separó las dos preguntas en chunks distintos."


def test_empty_text_returns_no_chunks(settings: Settings) -> None:
    chunker = Chunker(settings)
    assert chunker.chunk("", _build_source()) == []
    assert chunker.chunk("   \n\n\t   ", _build_source()) == []


def test_preprocess_strips_yaml_front_matter(settings: Settings) -> None:
    chunker = Chunker(settings)
    text: str = (
        "---\n"
        "id: foo\n"
        "title: Bar\n"
        "topics: [hypertrophy]\n"
        "---\n\n"
        "# Cuerpo\n\n"
        "Este es el contenido real."
    )
    cleaned = chunker.preprocess(text, SourceType.GUIDELINE)
    assert "id: foo" not in cleaned
    assert "title: Bar" not in cleaned
    assert "topics:" not in cleaned
    assert "Este es el contenido real." in cleaned
    assert "# Cuerpo" in cleaned


def test_chunks_do_not_include_front_matter(settings: Settings) -> None:
    """El contenido de los chunks no debe arrastrar metadata del front matter."""
    chunker = Chunker(settings)
    text: str = (
        "---\n"
        "id: vid-x\n"
        "title: Vídeo de prueba\n"
        "author: Fran\n"
        "topics: [hypertrophy]\n"
        "---\n\n"
    ) + "Contenido real del vídeo. " * 60

    chunks = chunker.chunk(text, _build_source(SourceType.VIDEO_TRANSCRIPT))
    assert chunks
    full = " ".join(c.content for c in chunks)
    assert "id: vid-x" not in full
    assert "title: Vídeo de prueba" not in full
    assert "topics:" not in full


def test_collapses_excessive_blank_lines(settings: Settings) -> None:
    chunker = Chunker(settings)
    text: str = "primera línea\n\n\n\n\n\nsegunda línea"
    cleaned = chunker.preprocess(text, SourceType.GUIDELINE)
    # Tres o más saltos consecutivos se compactan a dos.
    assert "\n\n\n" not in cleaned
    assert "primera línea" in cleaned
    assert "segunda línea" in cleaned
