"""Indexador de fuentes de conocimiento sobre ChromaDB.

Responsabilidades:
- Leer cada `KnowledgeSource`, chunkearla y embeber sus chunks.
- Persistir los embeddings en una colección ChromaDB de disco.
- Mantener idempotencia: re-indexar una misma fuente nunca duplica entradas.

Esquema de IDs en ChromaDB
    Cada chunk se identifica por `f"{source_id}::{chunk_index}"`. Esto permite
    que `upsert` actualice in-place. Antes de cada `index_source` se borran los
    chunks anteriores de esa fuente para evitar huérfanos cuando el documento
    pasa de N a N-k chunks (cambios de tamaño / de texto).

Esquema de metadata
    ChromaDB solo acepta primitivos en metadata (str, int, float, bool). El
    campo `topics: list[Topic]` se aplana a:
      - `topics_csv`: lista en CSV para mostrar al usuario.
      - `t_<topic>`: bool por cada topic, para filtrar server-side con `where`.
    Además se incluye `reliability_rank: int` para el filtro `reliability_min`
    del retriever (PASO 7).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from src.config.settings import PROJECT_ROOT, Settings, get_settings
from src.knowledge.chunker import Chunk, Chunker
from src.knowledge.embeddings import EmbeddingManager
from src.knowledge.sources import KnowledgeRegistry, KnowledgeSource

_console: Console = Console()
_logger: logging.Logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    """Indexa documentos de conocimiento en ChromaDB de forma idempotente."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedding_manager: EmbeddingManager | None = None,
    ) -> None:
        """Inicializa el indexador y abre/crea la colección persistente."""
        self._settings: Settings = settings or get_settings()
        self._embeddings: EmbeddingManager = embedding_manager or EmbeddingManager(
            self._settings
        )
        self._chunker: Chunker = Chunker(self._settings)

        self._settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._client: chromadb.api.ClientAPI = chromadb.PersistentClient(
            path=str(self._settings.CHROMA_PERSIST_DIR),
        )
        self._collection: Collection = self._client.get_or_create_collection(
            name=self._settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # los embeddings los generamos nosotros
        )

    # ------------------------------------------------------------ Propiedades

    @property
    def collection(self) -> Collection:
        """Acceso a la colección subyacente (lo usará el retriever)."""
        return self._collection

    # --------------------------------------------------------- API principal

    def index_source(self, source: KnowledgeSource) -> int:
        """Indexa una fuente completa. Devuelve el número de chunks creados."""
        path: Path = self._resolve_path(source.file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Archivo de la fuente {source.id!r} no encontrado: {path}"
            )

        try:
            text: str = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Archivo {path} no se puede leer como UTF-8: {e}"
            ) from e

        chunks: list[Chunk] = self._chunker.chunk(text, source)
        if not chunks:
            _console.print(
                f"[yellow]⚠[/yellow] {source.id}: el documento no produjo chunks."
            )
            return 0

        ids: list[str] = [self._chunk_id(c.source_id, c.chunk_index) for c in chunks]
        documents: list[str] = [c.content for c in chunks]
        metadatas: list[dict[str, Any]] = [
            self._chunk_metadata(c, source) for c in chunks
        ]
        embeddings: list[list[float]] = self._embeddings.embed_documents(documents)

        # Borra chunks antiguos de esta fuente (idempotencia frente a cambios
        # que reduzcan el número de chunks). Después hace upsert de los nuevos.
        self._collection.delete(where={"source_id": source.id})
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=metadatas,  # type: ignore[arg-type]
        )

        _console.print(
            f"[green]✓[/green] {source.id}: {len(chunks)} chunks indexados."
        )
        return len(chunks)

    def index_all(self, registry_path: Path | str | None = None) -> dict[str, Any]:
        """Indexa todas las fuentes del registry. Devuelve estadísticas y errores."""
        path: Path = Path(registry_path) if registry_path else self._settings.registry_path
        registry: KnowledgeRegistry = KnowledgeRegistry(path)
        sources: list[KnowledgeSource] = registry.list_all()

        if not sources:
            _console.print("[yellow]El registry está vacío.[/yellow]")
            return {
                "sources_processed": 0,
                "sources_failed": 0,
                "total_chunks": 0,
                "errors": [],
            }

        total_chunks: int = 0
        errors: list[dict[str, str]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=_console,
            transient=False,
        ) as progress:
            task = progress.add_task("Indexando fuentes…", total=len(sources))
            for source in sources:
                progress.update(task, description=f"[cyan]{source.id}[/cyan]")
                try:
                    total_chunks += self.index_source(source)
                except Exception as exc:  # noqa: BLE001 — capturamos para reportar
                    _logger.exception("Error indexando %s", source.id)
                    errors.append({"source_id": source.id, "error": str(exc)})
                progress.advance(task)

        return {
            "sources_processed": len(sources) - len(errors),
            "sources_failed": len(errors),
            "total_chunks": total_chunks,
            "errors": errors,
        }

    def reindex_source(self, source_id: str) -> int:
        """Reindexa una fuente concreta (idempotente). Lanza si no está en el registry."""
        registry: KnowledgeRegistry = KnowledgeRegistry(self._settings.registry_path)
        source: KnowledgeSource | None = registry.get(source_id)
        if source is None:
            raise KeyError(
                f"Fuente {source_id!r} no encontrada en el registry "
                f"({self._settings.registry_path})."
            )
        return self.index_source(source)

    def delete_source(self, source_id: str) -> int:
        """Elimina los chunks de una fuente del índice. Devuelve cuántos había."""
        existing: dict[str, Any] = self._collection.get(
            where={"source_id": source_id}, include=[]
        )
        n: int = len(existing.get("ids", []) or [])
        if n > 0:
            self._collection.delete(where={"source_id": source_id})
            _console.print(
                f"[red]✗[/red] {source_id}: {n} chunks eliminados del índice."
            )
        else:
            _console.print(f"[yellow]{source_id}: sin chunks que eliminar.[/yellow]")
        return n

    def get_stats(self) -> dict[str, Any]:
        """Devuelve estadísticas globales de la colección."""
        total: int = self._collection.count()

        # Para conocer source_ids únicos hay que leer la metadata.
        # Para colecciones de tamaño moderado (<10k chunks) es asumible.
        source_ids: set[str] = set()
        if total > 0:
            payload: dict[str, Any] = self._collection.get(include=["metadatas"])
            for md in payload.get("metadatas") or []:
                if md and "source_id" in md:
                    source_ids.add(str(md["source_id"]))

        return {
            "total_chunks": total,
            "unique_sources": len(source_ids),
            "source_ids": sorted(source_ids),
            "collection_name": self._settings.COLLECTION_NAME,
            "persist_dir": str(self._settings.CHROMA_PERSIST_DIR),
            "embedding_model": self._embeddings.model_name,
        }

    # ----------------------------------------------------------------- Helpers

    @staticmethod
    def _chunk_id(source_id: str, chunk_index: int) -> str:
        """ID estable y único de un chunk dentro de una fuente."""
        return f"{source_id}::{chunk_index}"

    @staticmethod
    def _chunk_metadata(chunk: Chunk, source: KnowledgeSource) -> dict[str, Any]:
        """Aplana la metadata del chunk a primitivos aceptados por ChromaDB."""
        md: dict[str, Any] = {
            "source_id": chunk.source_id,
            "chunk_index": chunk.chunk_index,
            "source_type": chunk.source_type.value,
            "author": chunk.author,
            "reliability": chunk.reliability.value,
            "reliability_rank": chunk.reliability.rank,
            "topics_csv": ",".join(t.value for t in chunk.topics),
            "title": source.title,
            "language": source.language,
        }
        # `url` es opcional: ChromaDB no acepta None, así que solo se añade si existe.
        if source.url:
            md["url"] = source.url
        # Boolean flags por topic → permite filtrado server-side con `where`.
        for topic in chunk.topics:
            md[f"t_{topic.value}"] = True
        return md

    @staticmethod
    def _resolve_path(file_path: str) -> Path:
        """Resuelve `KnowledgeSource.file_path` (relativo) contra la raíz del proyecto."""
        p: Path = Path(file_path)
        return p if p.is_absolute() else PROJECT_ROOT / p
