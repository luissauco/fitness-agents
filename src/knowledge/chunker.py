"""Chunking inteligente con metadata heredada de la `KnowledgeSource`.

Características:
- Usa `RecursiveCharacterTextSplitter` de LangChain.
- Separadores específicos para transcripciones de vídeo y para papers científicos.
- Preprocesado: elimina timestamps de subtítulos y marcadores tipo `[música]`.
- Hereda metadata (`source_id`, `chunk_index`, `topics`, `reliability`, `author`,
  `source_type`) en cada chunk para que el indexador pueda guardarla en ChromaDB.

Nota sobre el tamaño:
    `CHUNK_SIZE` y `CHUNK_OVERLAP` se interpretan en CARACTERES (no tokens). Es la unidad
    nativa del splitter recursivo y resulta más predecible. La equivalencia aproximada
    para texto en español es ~4-5 caracteres por token. El modelo de embeddings que se
    elija en el `PASO 5` debe tener un contexto suficiente para esta longitud (≈ 250
    tokens si CHUNK_SIZE=1000).
"""

from __future__ import annotations

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ConfigDict

from src.config.settings import Settings, get_settings
from src.knowledge.sources import KnowledgeSource, Reliability, SourceType, Topic

# --------------------------------------------------------------------- Separadores

# El splitter recursivo prueba en orden: si un separador divide el texto en
# fragmentos del tamaño objetivo, lo usa; si no, baja al siguiente más fino.

_TRANSCRIPT_SEPARATORS: list[str] = [
    "\n## ",            # secciones markdown (preguntas, temas)
    "\n### ",
    "\n\nPregunta:",    # estructuras Q&A típicas en transcripciones
    "\nPregunta:",
    "\nP:",
    "\n¿",              # nuevas preguntas en español
    "\n\n",
    "\n",
    ". ",
    "? ",
    "! ",
    " ",
    "",
]

_PAPER_SEPARATORS: list[str] = [
    "\n# ",
    "\n## ",
    "\n### ",
    "\nAbstract",
    "\nIntroduction",
    "\nMethods",
    "\nMaterials and Methods",
    "\nResults",
    "\nDiscussion",
    "\nConclusion",
    "\nReferences",
    # equivalentes en español para papers traducidos o nacionales
    "\nResumen",
    "\nIntroducción",
    "\nMetodología",
    "\nResultados",
    "\nDiscusión",
    "\nConclusiones",
    "\nReferencias",
    "\n\n",
    "\n",
    ". ",
    " ",
    "",
]

_DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

# --------------------------------------------------------------------- Limpieza

# Patrones de timestamps y artefactos típicos de subtítulos/transcripciones.
_TIMESTAMP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\]"),  # [00:12], [00:12:34.500]
    re.compile(r"\(\d{1,2}:\d{2}(?::\d{2})?\)"),                  # (00:12)
    re.compile(
        r"^\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*$",
        re.MULTILINE,
    ),  # cabecera SRT/VTT
    re.compile(r"^\d+\s*$", re.MULTILINE),  # número de cue SRT en línea propia
]

# Marcadores de ruido como [música], [risas], (aplausos), etc.
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"[\[\(]\s*"
        r"(?:música|musica|music|risas|laughter|aplausos|applause|"
        r"silencio|silence|inaudible|ruido|noise|cheering|gritos)"
        r"\s*[\]\)]",
        re.IGNORECASE,
    ),
]

_HORIZONTAL_WS_RE: re.Pattern[str] = re.compile(r"[ \t]+")
_BLANK_LINES_RE: re.Pattern[str] = re.compile(r"\n{3,}")

# Front matter YAML al inicio del archivo (entre dos `---`). Es metadata, no
# contenido; debe quitarse antes de chunkear o se cuela en los embeddings.
_FRONT_MATTER_RE: re.Pattern[str] = re.compile(
    r"\A---\s*\n.*?\n---\s*\n",
    re.DOTALL,
)


# --------------------------------------------------------------------- Modelos


class Chunk(BaseModel):
    """Fragmento de texto con metadata heredada de la `KnowledgeSource`."""

    model_config = ConfigDict(use_enum_values=False)

    content: str
    source_id: str
    chunk_index: int
    source_type: SourceType
    author: str
    topics: list[Topic]
    reliability: Reliability


# --------------------------------------------------------------------- Chunker


class Chunker:
    """Divide documentos en chunks heredando metadata desde la `KnowledgeSource`."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Crea un chunker. Si no se pasa `settings`, usa el singleton."""
        self._settings: Settings = settings or get_settings()

    def chunk(self, text: str, source: KnowledgeSource) -> list[Chunk]:
        """Preprocesa el texto, lo divide y devuelve los chunks con metadata."""
        cleaned: str = self.preprocess(text, source.source_type)
        if not cleaned:
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._settings.CHUNK_SIZE,
            chunk_overlap=self._settings.CHUNK_OVERLAP,
            separators=self._separators_for(source.source_type),
            length_function=len,
            keep_separator=True,
        )
        pieces: list[str] = [p for p in splitter.split_text(cleaned) if p.strip()]

        return [
            Chunk(
                content=piece.strip(),
                source_id=source.id,
                chunk_index=i,
                source_type=source.source_type,
                author=source.author,
                topics=list(source.topics),
                reliability=source.reliability,
            )
            for i, piece in enumerate(pieces)
        ]

    def preprocess(self, text: str, source_type: SourceType) -> str:
        """Limpia el texto: front matter, timestamps, marcadores de ruido y espacios."""
        # El strip de front matter aplica a todos los tipos: lo añadimos en
        # transcripciones (video_ingest), guidelines (plantillas) y studies.
        cleaned: str = _FRONT_MATTER_RE.sub("", text, count=1)

        # La limpieza de timestamps solo aplica a transcripciones de vídeo.
        if source_type == SourceType.VIDEO_TRANSCRIPT:
            for pattern in _TIMESTAMP_PATTERNS:
                cleaned = pattern.sub("", cleaned)

        # Marcadores de ruido pueden aparecer en cualquier transcripción de audio.
        for pattern in _NOISE_PATTERNS:
            cleaned = pattern.sub("", cleaned)

        # Normaliza espacios y saltos de línea sin destruir párrafos.
        cleaned = _HORIZONTAL_WS_RE.sub(" ", cleaned)
        cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned)

        return cleaned.strip()

    @staticmethod
    def _separators_for(source_type: SourceType) -> list[str]:
        """Devuelve los separadores recursivos adecuados al tipo de documento."""
        if source_type == SourceType.VIDEO_TRANSCRIPT:
            return _TRANSCRIPT_SEPARATORS
        if source_type == SourceType.SCIENTIFIC_STUDY:
            return _PAPER_SEPARATORS
        return _DEFAULT_SEPARATORS
