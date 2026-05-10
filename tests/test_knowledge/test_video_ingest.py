"""Tests for video transcript ingestion helpers."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.config.settings import Settings
from src.knowledge.registry_sync import parse_front_matter
from src.knowledge.sources import KnowledgeSource, Reliability, SourceType, Topic
from src.knowledge.video_ingest import VideoIngester, _make_slug


def test_make_slug_keeps_video_id_when_title_is_truncated() -> None:
    title = "Desmintiendo mitos del gimnasio basado en ciencia " * 3

    first = _make_slug(title, "7515147905691438358")
    second = _make_slug(title, "7459132651128065313")

    assert first != second
    assert first.endswith("-7515147905691438358")
    assert second.endswith("-7459132651128065313")
    assert len(first) <= 55
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", first)


def test_persist_transcript_generates_unique_source_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.config.settings.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.knowledge.video_ingest.PROJECT_ROOT", tmp_path)
    settings = Settings(
        ANTHROPIC_API_KEY="test-key",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
    )
    ingester = VideoIngester(settings=settings)
    title = "Hablemos de el dorsal y como entrenarlo. " * 3

    source_a = ingester._persist_transcript(
        transcript="Transcripcion A",
        video_meta={"title": title, "id": "7320321936054095137"},
        url="https://www.tiktok.com/@franperezjurado/video/7320321936054095137",
        topics=[Topic.HYPERTROPHY],
        author="Fran Perez Jurado",
        reliability=Reliability.EXPERT_OPINION,
    )
    source_b = ingester._persist_transcript(
        transcript="Transcripcion B",
        video_meta={"title": title, "id": "7317002680868637985"},
        url="https://www.tiktok.com/@franperezjurado/video/7317002680868637985",
        topics=[Topic.HYPERTROPHY],
        author="Fran Perez Jurado",
        reliability=Reliability.EXPERT_OPINION,
    )

    assert source_a.id != source_b.id
    assert source_a.id.endswith("-7320321936054095137")
    assert source_b.id.endswith("-7317002680868637985")
    assert settings.transcripts_dir.joinpath(f"{source_a.id}.md").exists()
    assert settings.transcripts_dir.joinpath(f"{source_b.id}.md").exists()


def test_build_markdown_quotes_title_as_yaml_string(tmp_path: Path) -> None:
    source = KnowledgeSource(
        id="video-hashtag-title",
        title="#pegar un video con hashtags #gym",
        author="Fran Perez Jurado",
        source_type=SourceType.VIDEO_TRANSCRIPT,
        topics=[Topic.HYPERTROPHY],
        reliability=Reliability.EXPERT_OPINION,
        url="https://example.test/video",
        file_path="src/knowledge/data/transcripts/video-hashtag-title.md",
        language="es",
    )

    md_path = tmp_path / "video.md"
    md_path.write_text(
        VideoIngester._build_markdown(source, "Transcripcion", {}),
        encoding="utf-8",
    )

    front_matter = parse_front_matter(md_path)
    assert front_matter is not None
    assert front_matter["title"] == "#pegar un video con hashtags #gym"
