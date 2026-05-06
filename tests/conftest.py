"""Configuración compartida de los tests.

Establece `ANTHROPIC_API_KEY` en el entorno antes de cualquier import del
módulo de settings, ya que el modelo Pydantic la marca como obligatoria.
"""

from __future__ import annotations

import os

# `setdefault` no pisa la variable si el desarrollador ya la tiene definida.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from src.config.settings import Settings  # noqa: E402
from tests.helpers import FakeEmbeddingManager  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """`Settings` con persistencia y carpeta de caché bajo `tmp_path`."""
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        COLLECTION_NAME="test_kb",
        CHUNK_SIZE=200,
        CHUNK_OVERLAP=50,
    )


@pytest.fixture
def fake_embeddings() -> FakeEmbeddingManager:
    """Embedding manager ficticio (sin descarga de modelos)."""
    return FakeEmbeddingManager()
