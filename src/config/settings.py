"""Configuración global del sistema fitness-agents.

Carga las variables de entorno desde un archivo `.env` con `pydantic-settings`
y expone una instancia única (singleton mediante `lru_cache`) accesible a todo
el código vía `get_settings()`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto: dos niveles por encima de este archivo (src/config/settings.py).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Variables de configuración cargadas desde `.env` y/o el entorno."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # API de Claude
    ANTHROPIC_API_KEY: SecretStr = Field(
        ..., description="Clave de API de Anthropic (Claude)."
    )

    # ChromaDB
    CHROMA_PERSIST_DIR: Path = Field(
        default=PROJECT_ROOT / "src" / "knowledge" / "data" / "chroma_db",
        description="Directorio donde ChromaDB persiste el índice.",
    )
    COLLECTION_NAME: str = Field(
        default="fitness_knowledge",
        description="Nombre de la colección de ChromaDB.",
    )

    # Embeddings
    EMBEDDING_MODEL: str = Field(
        default="intfloat/multilingual-e5-small",
        description=(
            "Identificador del modelo de embeddings. Por defecto se usa un modelo "
            "multilingüe local de sentence-transformers, sin coste ni API key. "
            "El modelo `e5-small` soporta 512 tokens de contexto, suficiente para "
            "chunks de ~1000 caracteres en español."
        ),
    )

    # Chunking
    CHUNK_SIZE: int = Field(
        default=1000,
        ge=100,
        description="Tamaño objetivo de cada chunk (en caracteres aproximados).",
    )
    CHUNK_OVERLAP: int = Field(
        default=200,
        ge=0,
        description="Solapamiento entre chunks consecutivos.",
    )

    # Rutas derivadas (no se leen del entorno).
    @property
    def knowledge_data_dir(self) -> Path:
        """Carpeta `src/knowledge/data/` con transcripciones, estudios y guidelines."""
        return PROJECT_ROOT / "src" / "knowledge" / "data"

    @property
    def transcripts_dir(self) -> Path:
        """Carpeta de transcripciones de vídeos."""
        return self.knowledge_data_dir / "transcripts"

    @property
    def studies_dir(self) -> Path:
        """Carpeta de estudios científicos."""
        return self.knowledge_data_dir / "studies"

    @property
    def guidelines_dir(self) -> Path:
        """Carpeta de guidelines redactadas."""
        return self.knowledge_data_dir / "guidelines"

    @property
    def registry_path(self) -> Path:
        """Ruta del registry JSON con todas las fuentes indexadas."""
        return self.knowledge_data_dir / "registry.json"

    @property
    def embeddings_cache_dir(self) -> Path:
        """Carpeta local de caché de embeddings."""
        return PROJECT_ROOT / ".embeddings_cache"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve la instancia única de `Settings` (singleton via `lru_cache`)."""
    return Settings()  # type: ignore[call-arg]
