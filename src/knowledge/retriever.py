"""Recuperación semántica sobre la colección ChromaDB de la base de conocimiento.

Filtra por metadata server-side (topics, source_types, reliability, author),
calcula un score de similitud por cosine y formatea el contexto recuperado para
inyectarlo directamente en el prompt de un agente.

Score
    Como los embeddings están L2-normalizados, ChromaDB devuelve `distance`
    en `[0, 2]` (cosine_distance = 1 − cosine_similarity). Convertimos a un
    `score` ∈ `[0, 1]` con `score = max(0, 1 − distance)`. Cuanto más alto,
    más relevante. Un threshold de 0.3 filtra resultados poco relacionados
    sin ser demasiado estricto.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import chromadb
from chromadb.api.models.Collection import Collection
from pydantic import BaseModel, ConfigDict

from src.config.settings import Settings, get_settings
from src.knowledge.embeddings import EmbeddingManager
from src.knowledge.sources import Reliability, SourceType, Topic

_logger: logging.Logger = logging.getLogger(__name__)

AgentType = Literal["training", "nutrition", "assessment", "progress"]


# Mapeo agente → topics relevantes (definido en el prompt original).
_AGENT_TOPICS: dict[str, list[Topic]] = {
    "training": [
        Topic.HYPERTROPHY,
        Topic.PERIODIZATION,
        Topic.VOLUME,
        Topic.INTENSITY,
        Topic.EXERCISE_SELECTION,
        Topic.BIOMECHANICS,
        Topic.REST_PAUSE,
        Topic.SUPERSETS,
        Topic.DELOAD,
        Topic.PROGRESSIVE_OVERLOAD,
        Topic.MUSCLE_LENGTH,
        Topic.RESISTANCE_PROFILE,
    ],
    "nutrition": [
        Topic.NUTRITION,
        Topic.MACROS,
        Topic.MEAL_PLANNING,
        Topic.SUPPLEMENTS,
        Topic.CUTTING,
        Topic.BULKING,
        Topic.RECOMPOSITION,
        Topic.BODY_COMPOSITION,
    ],
    "assessment": [
        Topic.BODY_COMPOSITION,
        Topic.NUTRITION,
    ],
    # `progress` necesita contexto amplio: lista vacía = sin filtro de topic.
    "progress": [],
}


class RetrievedChunk(BaseModel):
    """Chunk devuelto por el retriever, con score y metadata estructurada."""

    model_config = ConfigDict(use_enum_values=False)

    content: str
    score: float
    source_id: str
    title: str
    author: str
    source_type: SourceType
    reliability: Reliability
    topics: list[Topic]
    chunk_index: int
    url: str | None = None


class KnowledgeRetriever:
    """Recupera conocimiento relevante del vector store con filtros opcionales."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedding_manager: EmbeddingManager | None = None,
    ) -> None:
        """Inicializa el retriever apuntando a la colección persistente."""
        self._settings: Settings = settings or get_settings()
        self._embeddings: EmbeddingManager = embedding_manager or EmbeddingManager(
            self._settings
        )
        self._client: chromadb.api.ClientAPI = chromadb.PersistentClient(
            path=str(self._settings.CHROMA_PERSIST_DIR),
        )
        self._collection: Collection = self._client.get_or_create_collection(
            name=self._settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    # ------------------------------------------------------------ Recuperación

    def retrieve(
        self,
        query: str,
        topics: list[Topic] | None = None,
        source_types: list[SourceType] | None = None,
        reliability_min: Reliability | None = None,
        author: str | None = None,
        k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[RetrievedChunk]:
        """Búsqueda semántica con filtros opcionales de metadata."""
        if k <= 0:
            return []

        query_embedding: list[float] = self._embeddings.embed_query(query)
        where: dict[str, Any] | None = self._build_where(
            topics, source_types, reliability_min, author
        )

        result: dict[str, Any] = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return self._parse_query_result(result, score_threshold)

    def retrieve_for_agent(
        self,
        query: str,
        agent_type: AgentType,
        k: int = 5,
    ) -> str:
        """Recuperación preconfigurada por agente. Devuelve el contexto formateado."""
        if agent_type not in _AGENT_TOPICS:
            raise ValueError(
                f"agent_type desconocido: {agent_type!r}. "
                f"Válidos: {sorted(_AGENT_TOPICS)}"
            )
        topics: list[Topic] | None = _AGENT_TOPICS[agent_type] or None
        chunks: list[RetrievedChunk] = self.retrieve(query, topics=topics, k=k)
        return self.format_context(chunks)

    # -------------------------------------------------------------- Formateo

    @staticmethod
    def format_context(chunks: list[RetrievedChunk]) -> str:
        """Formatea los chunks recuperados como contexto inyectable en un prompt."""
        if not chunks:
            return "(Sin contexto recuperado para esta consulta.)"

        blocks: list[str] = []
        for c in chunks:
            header: str = (
                f"[Fuente: {c.title} | Autor: {c.author} | "
                f"Tipo: {c.source_type.value} | Fiabilidad: {c.reliability.value}]"
            )
            blocks.append(f"---\n{header}\n{c.content}\n---")
        return "\n".join(blocks)

    # --------------------------------------------------------------- Helpers

    @staticmethod
    def _build_where(
        topics: list[Topic] | None,
        source_types: list[SourceType] | None,
        reliability_min: Reliability | None,
        author: str | None,
    ) -> dict[str, Any] | None:
        """Construye la cláusula `where` para ChromaDB a partir de los filtros."""
        clauses: list[dict[str, Any]] = []

        if author:
            clauses.append({"author": author})

        if source_types:
            clauses.append(
                {"source_type": {"$in": [st.value for st in source_types]}}
            )

        if reliability_min is not None:
            clauses.append({"reliability_rank": {"$gte": reliability_min.rank}})

        if topics:
            # Boolean-flag por topic: queremos chunks que tengan ALGUNO de los topics.
            topic_clauses: list[dict[str, Any]] = [
                {f"t_{t.value}": True} for t in topics
            ]
            clauses.append(
                topic_clauses[0] if len(topic_clauses) == 1 else {"$or": topic_clauses}
            )

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _parse_query_result(
        result: dict[str, Any],
        score_threshold: float,
    ) -> list[RetrievedChunk]:
        """Transforma la respuesta cruda de ChromaDB en `RetrievedChunk`s filtrados."""
        # ChromaDB devuelve listas anidadas (una por query); aquí solo enviamos una.
        documents: list[str] = (result.get("documents") or [[]])[0]
        metadatas: list[dict[str, Any]] = (result.get("metadatas") or [[]])[0]
        distances: list[float] = (result.get("distances") or [[]])[0]

        out: list[RetrievedChunk] = []
        for doc, md, dist in zip(documents, metadatas, distances, strict=True):
            score: float = max(0.0, 1.0 - float(dist))
            if score < score_threshold:
                continue
            out.append(_metadata_to_chunk(doc, md, score))
        return out


def _metadata_to_chunk(
    content: str,
    md: dict[str, Any],
    score: float,
) -> RetrievedChunk:
    """Reconstruye un `RetrievedChunk` desde la metadata aplanada de ChromaDB."""
    topics: list[Topic] = [
        Topic(t) for t in str(md.get("topics_csv", "")).split(",") if t
    ]
    return RetrievedChunk(
        content=content,
        score=score,
        source_id=str(md["source_id"]),
        title=str(md.get("title") or md["source_id"]),
        author=str(md["author"]),
        source_type=SourceType(md["source_type"]),
        reliability=Reliability(md["reliability"]),
        topics=topics,
        chunk_index=int(md["chunk_index"]),
        url=md.get("url") if md.get("url") else None,
    )
