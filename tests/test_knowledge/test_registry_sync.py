"""Tests del sync de registry desde front matter YAML."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import Settings
from src.knowledge.registry_sync import (
    front_matter_to_source,
    parse_front_matter,
    sync_registry,
)
from src.knowledge.sources import KnowledgeRegistry, Reliability, SourceType

# --------------------------------------------------------------- Fixtures


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige `PROJECT_ROOT` a `tmp_path` en los módulos que lo usan.

    Así los tests escriben sus archivos bajo `tmp_path` y el cálculo de
    rutas relativas en `front_matter_to_source` funciona sin tocar el
    proyecto real.
    """
    monkeypatch.setattr("src.config.settings.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.knowledge.registry_sync.PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def settings_in_tmp(project_root: Path) -> Settings:
    """`Settings` cuyas carpetas de datos cuelgan de `project_root`."""
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        CHROMA_PERSIST_DIR=project_root / "chroma",
    )


# --------------------------------------------------------------- Helpers


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _filled_template(
    *,
    source_id: str = "tema-x",
    title: str = "Tema X",
    author: str = "Luis",
    source_type: str = "guideline",
    topics: tuple[str, ...] = ("hypertrophy",),
    reliability: str = "expert_opinion",
) -> str:
    topics_csv: str = ", ".join(topics)
    return (
        "---\n"
        f"id: {source_id}\n"
        f"title: {title}\n"
        f"author: {author}\n"
        f"source_type: {source_type}\n"
        f"topics: [{topics_csv}]\n"
        f"reliability: {reliability}\n"
        "language: es\n"
        "summary: \"Resumen breve.\"\n"
        "---\n\n"
        "# Cuerpo del documento\n"
    )


# --------------------------------------------------------------- Tests puros


def test_parse_front_matter_returns_dict(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    _write_md(md, _filled_template())
    fm = parse_front_matter(md)
    assert fm is not None
    assert fm["id"] == "tema-x"
    assert fm["topics"] == ["hypertrophy"]


def test_parse_front_matter_returns_none_without_block(tmp_path: Path) -> None:
    md = tmp_path / "plain.md"
    _write_md(md, "# Solo texto, sin front matter\n")
    assert parse_front_matter(md) is None


def test_front_matter_to_source_roundtrip(
    settings_in_tmp: Settings, project_root: Path
) -> None:
    md: Path = project_root / "src" / "knowledge" / "data" / "guidelines" / "doc.md"
    _write_md(md, _filled_template(source_id="round-trip"))
    fm = parse_front_matter(md)
    assert fm is not None

    source = front_matter_to_source(fm, md)
    assert source.id == "round-trip"
    assert source.author == "Luis"
    assert source.source_type == SourceType.GUIDELINE
    assert source.reliability == Reliability.EXPERT_OPINION
    assert source.file_path.endswith("doc.md")
    assert "src/knowledge/data/guidelines" in source.file_path


# --------------------------------------------------------------- Tests sync


def test_sync_adds_new_filled_template(
    settings_in_tmp: Settings, project_root: Path
) -> None:
    _write_md(
        settings_in_tmp.guidelines_dir / "doc.md",
        _filled_template(source_id="abc-123"),
    )

    result = sync_registry(settings_in_tmp)

    assert result.added == ["abc-123"]
    assert result.skipped == []
    assert result.errors == []
    registry = KnowledgeRegistry(settings_in_tmp.registry_path)
    assert "abc-123" in registry


def test_sync_skips_unfilled_template(
    settings_in_tmp: Settings,
) -> None:
    _write_md(
        settings_in_tmp.guidelines_dir / "unfilled.md",
        _filled_template(source_id="unfilled-doc", author=""),
    )

    result = sync_registry(settings_in_tmp)

    assert "unfilled-doc" not in result.added
    assert "unfilled-doc" not in result.updated
    assert any("unfilled.md" in path for path, _ in result.skipped)


def test_sync_skips_files_without_front_matter(
    settings_in_tmp: Settings,
) -> None:
    _write_md(
        settings_in_tmp.guidelines_dir / "plain.md",
        "# Solo cuerpo, ningún front matter.\n",
    )
    result = sync_registry(settings_in_tmp)
    assert any(
        "plain.md" in path and "front matter" in reason
        for path, reason in result.skipped
    )


def test_sync_is_idempotent(settings_in_tmp: Settings) -> None:
    _write_md(
        settings_in_tmp.guidelines_dir / "doc.md",
        _filled_template(source_id="idem-doc"),
    )

    first = sync_registry(settings_in_tmp)
    assert first.added == ["idem-doc"]

    second = sync_registry(settings_in_tmp)
    assert second.added == []
    assert second.updated == []
    assert second.unchanged == ["idem-doc"]


def test_sync_detects_updates(settings_in_tmp: Settings) -> None:
    md_path = settings_in_tmp.guidelines_dir / "doc.md"
    _write_md(md_path, _filled_template(source_id="upd-doc", author="Luis"))
    sync_registry(settings_in_tmp)

    # Cambio de autor en el front matter.
    _write_md(md_path, _filled_template(source_id="upd-doc", author="Otro"))
    result = sync_registry(settings_in_tmp)

    assert result.updated == ["upd-doc"]
    registry = KnowledgeRegistry(settings_in_tmp.registry_path)
    src = registry.get("upd-doc")
    assert src is not None
    assert src.author == "Otro"


def test_sync_dry_run_does_not_write(settings_in_tmp: Settings) -> None:
    _write_md(
        settings_in_tmp.guidelines_dir / "doc.md",
        _filled_template(source_id="dry-doc"),
    )

    result = sync_registry(settings_in_tmp, dry_run=True)

    assert result.added == ["dry-doc"]
    # En dry-run el registry no debe haberse escrito.
    assert not settings_in_tmp.registry_path.exists() or (
        "dry-doc" not in KnowledgeRegistry(settings_in_tmp.registry_path)
    )


def test_sync_reports_validation_errors(settings_in_tmp: Settings) -> None:
    """Un front matter con un topic inválido se reporta como error, no como crash."""
    bad: str = (
        "---\n"
        "id: bad-doc\n"
        "title: Mal documento\n"
        "author: Luis\n"
        "source_type: guideline\n"
        "topics: [topic-que-no-existe]\n"
        "reliability: expert_opinion\n"
        "---\n\n"
        "Cuerpo.\n"
    )
    _write_md(settings_in_tmp.guidelines_dir / "bad.md", bad)

    result = sync_registry(settings_in_tmp)

    assert result.added == []
    assert any("bad.md" in path for path, _ in result.errors)


def test_sync_picks_up_transcripts_too(settings_in_tmp: Settings) -> None:
    _write_md(
        settings_in_tmp.transcripts_dir / "video1.md",
        _filled_template(
            source_id="vid-1",
            source_type="video_transcript",
            author="Fran",
        ),
    )
    result = sync_registry(settings_in_tmp)
    assert result.added == ["vid-1"]
