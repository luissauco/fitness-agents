"""Generación de embeddings con caché local.

Por qué `sentence-transformers` (local) en lugar de Voyage AI / Anthropic:

1. **Coste cero**: ningún proveedor cobra por embeddings, incluso si re-indexamos
   cientos de veces durante el desarrollo.
2. **Sin API key adicional**: Anthropic no expone un endpoint de embeddings propio
   y Voyage requiere una clave separada que sería otra cosa que rotar.
3. **Sin latencia de red**: cada query del retriever sería un round-trip extra a
   un servicio externo. Local = milisegundos.
4. **Privacidad**: el contenido de los divulgadores y los planes del usuario
   no sale de la máquina.
5. **Calidad suficiente**: los modelos `e5` multilingües (Microsoft, MIT) están
   en lo más alto de MTEB/MIRACL para español y rinden de sobra para este caso.

Modelo por defecto: `intfloat/multilingual-e5-small` (384 dims, 512 tokens de
contexto, ~120MB). Para más calidad: `intfloat/multilingual-e5-base` (768 dims,
~280MB) o `BAAI/bge-m3` (1024 dims, 8192 tokens, ~2.2GB).

Detalle E5: estos modelos esperan prefijos `query: ` y `passage: ` en los textos
para distinguir consultas de documentos. Esta clase los aplica automáticamente.
"""

from __future__ import annotations

import hashlib
import pickle
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from src.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_FILENAME_SAFE_RE: re.Pattern[str] = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Sanea un nombre de modelo (`intfloat/multilingual-e5-small`) para usarlo como filename."""
    return _FILENAME_SAFE_RE.sub("_", name)


class _EmbeddingCache:
    """Caché de embeddings persistido en disco como un pickle por modelo."""

    def __init__(self, cache_dir: Path, model_name: str) -> None:
        self._dir: Path = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path: Path = cache_dir / f"{_safe_filename(model_name)}.pkl"
        self._cache: dict[str, list[float]] = self._load()
        self._dirty: bool = False
        self._lock: threading.Lock = threading.Lock()

    def get(self, text: str) -> list[float] | None:
        """Devuelve el embedding cacheado para `text`, o `None` si no existe."""
        return self._cache.get(self._key(text))

    def put(self, text: str, vector: list[float]) -> None:
        """Almacena un embedding en la caché en memoria (no persiste hasta `flush`)."""
        with self._lock:
            self._cache[self._key(text)] = vector
            self._dirty = True

    def flush(self) -> None:
        """Persiste a disco si hay cambios pendientes (escritura atómica)."""
        with self._lock:
            if not self._dirty:
                return
            tmp: Path = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("wb") as f:
                pickle.dump(self._cache, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(self._path)
            self._dirty = False

    def __len__(self) -> int:
        return len(self._cache)

    @staticmethod
    def _key(text: str) -> str:
        """SHA-256 del texto. Usamos hash para evitar problemas con keys muy largas."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load(self) -> dict[str, list[float]]:
        """Carga la caché desde disco. Si el archivo está corrupto, empieza vacía."""
        if not self._path.exists():
            return {}
        try:
            with self._path.open("rb") as f:
                return pickle.load(f)
        except (pickle.UnpicklingError, EOFError):
            return {}


class EmbeddingManager:
    """Encapsula la generación de embeddings y abstrae al proveedor.

    Carga el modelo de forma perezosa (la primera llamada que necesite
    inferencia descarga y carga el modelo en memoria). Aplica los prefijos
    específicos de los modelos `e5` de forma transparente.
    """

    _E5_QUERY_PREFIX: str = "query: "
    _E5_PASSAGE_PREFIX: str = "passage: "

    def __init__(self, settings: Settings | None = None) -> None:
        """Crea el manager. Si no se pasa `settings`, usa el singleton."""
        self._settings: Settings = settings or get_settings()
        self._model_name: str = self._settings.EMBEDDING_MODEL
        self._cache: _EmbeddingCache = _EmbeddingCache(
            self._settings.embeddings_cache_dir, self._model_name
        )
        self._model: SentenceTransformer | None = None

    # ---------------------------------------------------------- API pública

    @property
    def model_name(self) -> str:
        """Identificador del modelo activo (útil para logs/metadatos)."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Dimensionalidad de los vectores que produce el modelo."""
        dim = self._lazy_model().get_sentence_embedding_dimension()
        if dim is None:
            raise RuntimeError(
                f"El modelo {self._model_name!r} no expone dimensionalidad."
            )
        return dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para textos a almacenar (chunks/passages)."""
        if not texts:
            return []
        return self._embed(texts, prefix=self._passage_prefix())

    def embed_query(self, text: str) -> list[float]:
        """Genera el embedding de una consulta."""
        vectors: list[list[float]] = self._embed([text], prefix=self._query_prefix())
        return vectors[0]

    # ---------------------------------------------------------- Internos

    def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        """Aplica prefijo, consulta caché y solo computa los faltantes."""
        prefixed: list[str] = [prefix + t for t in texts]
        results: list[list[float] | None] = [self._cache.get(t) for t in prefixed]

        missing_indices: list[int] = [i for i, v in enumerate(results) if v is None]
        if missing_indices:
            to_compute: list[str] = [prefixed[i] for i in missing_indices]
            new_vectors: list[list[float]] = self._lazy_model().encode(
                to_compute,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).tolist()
            for idx, vec in zip(missing_indices, new_vectors, strict=True):
                self._cache.put(prefixed[idx], vec)
                results[idx] = vec
            self._cache.flush()

        # Tras rellenar los faltantes, ningún elemento debe ser None.
        return [v for v in results if v is not None]

    def _lazy_model(self) -> SentenceTransformer:
        """Carga el modelo la primera vez que se necesita."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    # ---- Prefijos E5 ------------------------------------------------------

    def _is_e5_model(self) -> bool:
        """Heurística: los nombres de los modelos E5 contienen `e5`."""
        return "e5" in self._model_name.lower()

    def _query_prefix(self) -> str:
        return self._E5_QUERY_PREFIX if self._is_e5_model() else ""

    def _passage_prefix(self) -> str:
        return self._E5_PASSAGE_PREFIX if self._is_e5_model() else ""
