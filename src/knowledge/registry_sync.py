"""Sincronización automática del `registry.json` desde el front matter YAML.

Escanea las carpetas de fuentes (`guidelines`, `transcripts`, `studies`) en
busca de archivos `.md` que tengan un bloque YAML al inicio del archivo
delimitado por `---`. Para cada uno, construye una `KnowledgeSource` y la
añade o actualiza en `registry.json`.

Reglas de filtrado:
    - Sin front matter → se salta.
    - `id` o `author` vacíos → se salta (plantilla aún no rellenada).
    - Fallo de validación Pydantic → se reporta como error, no se añade.

El sync es idempotente: ejecutarlo dos veces sobre el mismo estado no produce
cambios. Si las fuentes en disco se modifican, el siguiente sync detecta el
delta y reescribe `registry.json` solo si hay cambios reales.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config.settings import PROJECT_ROOT, Settings, get_settings
from src.knowledge.sources import (
    KnowledgeRegistry,
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)

# Front matter al inicio del archivo, entre dos líneas `---`.
_FRONT_MATTER_RE: re.Pattern[str] = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


class SyncResult(BaseModel):
    """Resumen del sync, fácil de imprimir desde el CLI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scanned: int = 0
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    skipped: list[tuple[str, str]] = Field(default_factory=list)
    errors: list[tuple[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------- Helpers


def parse_front_matter(md_path: Path) -> dict[str, Any] | None:
    """Devuelve el front matter como dict, o `None` si el archivo no tiene."""
    content: str = md_path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(content)
    if match is None:
        return None
    parsed: Any = yaml.safe_load(match.group(1)) or {}
    return parsed if isinstance(parsed, dict) else None


def front_matter_to_source(
    fm: dict[str, Any], md_path: Path
) -> KnowledgeSource:
    """Construye una `KnowledgeSource` a partir de un dict de front matter."""
    topics_raw: list[str] = list(fm.get("topics") or [])
    topics: list[Topic] = [Topic(t) for t in topics_raw]

    rel_path: str = str(md_path.resolve().relative_to(PROJECT_ROOT))

    return KnowledgeSource(
        id=fm["id"],
        title=fm["title"],
        author=fm["author"],
        source_type=SourceType(fm["source_type"]),
        topics=topics,
        reliability=Reliability(fm.get("reliability") or "expert_opinion"),
        date_published=fm.get("date_published") or None,
        url=_clean_str(fm.get("url")),
        file_path=rel_path,
        language=fm.get("language") or "es",
        summary=_clean_str(fm.get("summary")),
    )


def _clean_str(value: Any) -> str | None:
    """Normaliza `''` → `None` para no propagar strings vacíos a Pydantic."""
    if value is None:
        return None
    text: str = str(value).strip()
    return text or None


# ---------------------------------------------------------------- API


def sync_registry(
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Sincroniza `registry.json` con el front matter de los `.md` del proyecto."""
    settings = settings or get_settings()
    registry: KnowledgeRegistry = KnowledgeRegistry(settings.registry_path)
    result: SyncResult = SyncResult()

    folders: list[Path] = [
        settings.guidelines_dir,
        settings.transcripts_dir,
        settings.studies_dir,
    ]
    md_files: list[Path] = []
    for folder in folders:
        if folder.exists():
            md_files.extend(sorted(folder.glob("*.md")))
    result.scanned = len(md_files)

    for md_path in md_files:
        rel_path: str = str(md_path.resolve().relative_to(PROJECT_ROOT))
        fm: dict[str, Any] | None = parse_front_matter(md_path)

        if fm is None:
            result.skipped.append((rel_path, "sin front matter YAML"))
            continue

        # Plantillas no rellenadas: id o author en blanco.
        if not _clean_str(fm.get("id")):
            result.skipped.append((rel_path, "id vacío"))
            continue
        if not _clean_str(fm.get("author")):
            result.skipped.append(
                (rel_path, "author vacío (plantilla no rellenada)")
            )
            continue

        try:
            source: KnowledgeSource = front_matter_to_source(fm, md_path)
        except (KeyError, ValueError, ValidationError) as exc:
            result.errors.append((rel_path, str(exc)))
            continue

        existing: KnowledgeSource | None = registry.get(source.id)
        if existing is None:
            if not dry_run:
                registry.add(source)
            result.added.append(source.id)
        elif existing != source:
            if not dry_run:
                registry.add(source, overwrite=True)
            result.updated.append(source.id)
        else:
            result.unchanged.append(source.id)

    if not dry_run and (result.added or result.updated):
        registry.save()

    return result
