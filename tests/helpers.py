"""Utilidades reutilizables por los tests del módulo `knowledge`."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.knowledge.sources import (
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)


class FakeEmbeddingManager:
    """`EmbeddingManager` ficticio: vectores deterministas a partir de SHA-256.

    Evita descargar modelos en los tests. Los vectores quedan en el orto-positivo
    (componentes en [0, 1)), por lo que la similitud coseno entre cualquier par
    es no negativa y el threshold de 0.3 del retriever no descarta resultados de
    forma trivial.
    """

    DIMENSION: int = 8
    model_name: str = "fake-test-model"

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        digest: bytes = hashlib.sha256(text.encode("utf-8")).digest()
        raw: list[float] = [b / 256.0 for b in digest[: cls.DIMENSION]]
        norm: float = sum(x * x for x in raw) ** 0.5 or 1.0
        return [x / norm for x in raw]


def make_source(
    source_id: str,
    *,
    text: str,
    file_path: Path,
    title: str | None = None,
    author: str = "Test Author",
    source_type: SourceType = SourceType.GUIDELINE,
    topics: list[Topic] | None = None,
    reliability: Reliability = Reliability.EXPERT_OPINION,
) -> KnowledgeSource:
    """Crea un archivo de texto en `file_path` y devuelve la `KnowledgeSource`."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")
    return KnowledgeSource(
        id=source_id,
        title=title or source_id,
        author=author,
        source_type=source_type,
        topics=topics or [Topic.HYPERTROPHY],
        reliability=reliability,
        file_path=str(file_path),
    )
