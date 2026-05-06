"""Modelos de fuentes de la base de conocimiento y registro persistente.

Define los enums (`SourceType`, `Topic`, `Reliability`) y el modelo `KnowledgeSource`
que describe cada documento indexado, junto con la clase `KnowledgeRegistry`
que actúa como catálogo persistido en `registry.json`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Patrón para validar slugs: minúsculas, números y guiones; comienza/termina en alfanumérico.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SourceType(str, Enum):
    """Tipo de fuente documental."""

    VIDEO_TRANSCRIPT = "video_transcript"
    SCIENTIFIC_STUDY = "scientific_study"
    GUIDELINE = "guideline"
    BOOK_EXCERPT = "book_excerpt"
    ARTICLE = "article"


class Topic(str, Enum):
    """Temáticas de hipertrofia, entrenamiento y nutrición."""

    HYPERTROPHY = "hypertrophy"
    NUTRITION = "nutrition"
    PERIODIZATION = "periodization"
    BIOMECHANICS = "biomechanics"
    EXERCISE_SELECTION = "exercise_selection"
    VOLUME = "volume"
    INTENSITY = "intensity"
    REST_PAUSE = "rest_pause"
    SUPERSETS = "supersets"
    BODY_COMPOSITION = "body_composition"
    SUPPLEMENTS = "supplements"
    RECOVERY = "recovery"
    NEAT_CARDIO = "neat_cardio"
    MACROS = "macros"
    MEAL_PLANNING = "meal_planning"
    CUTTING = "cutting"
    BULKING = "bulking"
    RECOMPOSITION = "recomposition"
    DELOAD = "deload"
    PROGRESSIVE_OVERLOAD = "progressive_overload"
    MUSCLE_LENGTH = "muscle_length"
    RESISTANCE_PROFILE = "resistance_profile"


class Reliability(str, Enum):
    """Nivel de fiabilidad de la fuente. El orden refleja jerarquía creciente."""

    ANECDOTAL = "anecdotal"
    EXPERT_OPINION = "expert_opinion"
    PEER_REVIEWED = "peer_reviewed"
    META_ANALYSIS = "meta_analysis"

    @property
    def rank(self) -> int:
        """Posición numérica (mayor = más fiable). Útil para filtros `reliability_min`."""
        order = {
            Reliability.ANECDOTAL: 0,
            Reliability.EXPERT_OPINION: 1,
            Reliability.PEER_REVIEWED: 2,
            Reliability.META_ANALYSIS: 3,
        }
        return order[self]


class KnowledgeSource(BaseModel):
    """Documento individual de la base de conocimiento."""

    model_config = ConfigDict(use_enum_values=False, str_strip_whitespace=True)

    id: str = Field(
        ...,
        min_length=3,
        max_length=80,
        description="Slug único de la fuente (minúsculas, números y guiones).",
    )
    title: str = Field(..., min_length=1, max_length=300)
    author: str = Field(..., min_length=1, max_length=200)
    source_type: SourceType
    topics: list[Topic] = Field(..., min_length=1)
    reliability: Reliability
    date_published: date | None = None
    url: str | None = None
    file_path: str = Field(
        ...,
        description=(
            "Ruta relativa (desde la raíz del proyecto) al archivo de texto que "
            "contiene el contenido indexable de la fuente."
        ),
    )
    language: str = Field(default="es", min_length=2, max_length=5)
    summary: str | None = Field(default=None, max_length=2000)

    @field_validator("id")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"`id` debe ser un slug en kebab-case (a-z, 0-9, guiones): {v!r}"
            )
        return v

    @field_validator("topics")
    @classmethod
    def _topics_unique(cls, v: list[Topic]) -> list[Topic]:
        if len(set(v)) != len(v):
            raise ValueError("`topics` no puede contener duplicados.")
        return v


class KnowledgeRegistry:
    """Catálogo persistente de las fuentes indexadas.

    Wrappea un archivo JSON con la forma:

        {
            "version": "1.0",
            "sources": [ {KnowledgeSource}, ... ]
        }

    Las operaciones modifican el estado en memoria; `save()` lo persiste en disco.
    """

    VERSION: str = "1.0"

    def __init__(self, path: Path) -> None:
        """Crea (o carga) el registry en la ruta indicada."""
        self.path: Path = path
        self._sources: dict[str, KnowledgeSource] = {}
        if path.exists():
            self.load()

    # ------------------------------------------------------------------ I/O

    def load(self) -> None:
        """Carga las fuentes desde disco, sobreescribiendo el estado en memoria."""
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        sources = raw.get("sources", [])
        self._sources = {
            entry["id"]: KnowledgeSource.model_validate(entry) for entry in sources
        }

    def save(self) -> None:
        """Persiste el estado actual en disco (creando el directorio si no existe)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "sources": [
                src.model_dump(mode="json", exclude_none=True)
                for src in self._sources.values()
            ],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ----------------------------------------------------------------- CRUD

    def add(self, source: KnowledgeSource, *, overwrite: bool = False) -> None:
        """Añade una fuente al registry. Lanza `ValueError` si ya existe y `overwrite=False`."""
        if source.id in self._sources and not overwrite:
            raise ValueError(f"Ya existe una fuente con id={source.id!r}.")
        self._sources[source.id] = source

    def remove(self, source_id: str) -> bool:
        """Elimina una fuente. Devuelve `True` si existía, `False` si no."""
        return self._sources.pop(source_id, None) is not None

    def get(self, source_id: str) -> KnowledgeSource | None:
        """Devuelve la fuente con `source_id` o `None` si no existe."""
        return self._sources.get(source_id)

    def list_all(self) -> list[KnowledgeSource]:
        """Lista todas las fuentes registradas."""
        return list(self._sources.values())

    def __contains__(self, source_id: object) -> bool:
        return isinstance(source_id, str) and source_id in self._sources

    def __len__(self) -> int:
        return len(self._sources)

    # ----------------------------------------------------------- Constructors

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Constructor explícito desde una ruta (alias de `__init__` para legibilidad)."""
        return cls(path)
