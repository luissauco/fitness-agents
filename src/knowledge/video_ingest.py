"""Pipeline de ingesta de vídeos: descarga → transcripción → indexado.

Pasos:
  1. Descarga el audio del vídeo (TikTok, YouTube, etc.) con `yt-dlp`.
  2. Transcribe a texto con `faster-whisper` (modelo multilingüe local).
  3. Escribe un Markdown con front matter en `data/transcripts/`.
  4. Añade la fuente al `registry.json`.
  5. (Opcional) Lanza la indexación en ChromaDB inmediatamente.

Uso desde CLI:
    python -m src.knowledge.video_ingest <url> --topics hypertrophy,volume

Requisitos del sistema:
    - `ffmpeg` instalado y en el PATH (lo usan tanto yt-dlp como faster-whisper).
    - Conexión a internet la primera vez (para descargar el modelo Whisper).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Cuando este módulo se ejecuta como `python -m src.knowledge.video_ingest`,
# necesitamos cargar `.env` en `os.environ` para que `huggingface_hub` lea
# `HF_TOKEN`. Llamarlo a nivel de módulo es seguro (no-op si no hay `.env`).
load_dotenv()

from src.config.settings import PROJECT_ROOT, Settings, get_settings
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.sources import (
    KnowledgeRegistry,
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

_console: Console = Console()
_logger: logging.Logger = logging.getLogger(__name__)

# Patrones para slugificar.
_SLUG_REPLACE_RE: re.Pattern[str] = re.compile(r"[^a-z0-9]+")
_ACCENTS_TABLE: dict[int, int | None] = str.maketrans(
    "áéíóúüñçÁÉÍÓÚÜÑÇ", "aeiouuncAEIOUUNC"
)


def _slugify(text: str, *, max_len: int = 60) -> str:
    """Convierte un texto arbitrario en un slug seguro para `KnowledgeSource.id`."""
    text = text.translate(_ACCENTS_TABLE).lower()
    text = _SLUG_REPLACE_RE.sub("-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "video"


# ---------------------------------------------------------- VideoIngester


class VideoIngester:
    """Encadena descarga, transcripción y registro de un vídeo en la KB."""

    DEFAULT_AUTHOR: str = "Fran Pérez Jurado"
    DEFAULT_RELIABILITY: Reliability = Reliability.EXPERT_OPINION
    DEFAULT_WHISPER_MODEL: str = "small"
    DEFAULT_WHISPER_COMPUTE_TYPE: str = "int8"

    def __init__(
        self,
        settings: Settings | None = None,
        indexer: KnowledgeIndexer | None = None,
        whisper_model: str | None = None,
        whisper_compute_type: str | None = None,
    ) -> None:
        """Crea el ingester. `indexer` es opcional; si se omite, no auto-indexa."""
        self._settings: Settings = settings or get_settings()
        self._indexer: KnowledgeIndexer | None = indexer
        self._whisper_model_name: str = whisper_model or self.DEFAULT_WHISPER_MODEL
        self._whisper_compute_type: str = (
            whisper_compute_type or self.DEFAULT_WHISPER_COMPUTE_TYPE
        )
        self._whisper: WhisperModel | None = None

    # -------------------------------------------------------------- API

    def ingest(
        self,
        url: str,
        topics: list[Topic],
        *,
        author: str | None = None,
        reliability: Reliability | None = None,
        do_index: bool = True,
    ) -> KnowledgeSource:
        """Pipeline completo. Devuelve la `KnowledgeSource` creada y registrada."""
        if not topics:
            raise ValueError("Debes indicar al menos un topic.")

        author_value: str = author or self.DEFAULT_AUTHOR
        reliability_value: Reliability = reliability or self.DEFAULT_RELIABILITY

        with tempfile.TemporaryDirectory(prefix="fitness-agents-") as tmpdir:
            tmp_path: Path = Path(tmpdir)
            downloaded, video_meta = self._download_audio(url, tmp_path)
            wav_path: Path = self._extract_wav(downloaded, tmp_path)
            transcript: str = self._transcribe(wav_path)

        source: KnowledgeSource = self._persist_transcript(
            transcript=transcript,
            video_meta=video_meta,
            url=url,
            topics=topics,
            author=author_value,
            reliability=reliability_value,
        )

        if do_index and self._indexer is not None:
            self._indexer.index_source(source)

        return source

    # ----------------------------------------------------- Listado de perfil

    @staticmethod
    def list_profile_videos(profile_url: str) -> list[dict[str, Any]]:
        """Lista los vídeos de un perfil sin descargarlos. Solo metadata."""
        import yt_dlp

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,  # solo metadata, no descarga
            "noprogress": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(profile_url, download=False)
        entries: list[dict[str, Any]] = list(info.get("entries") or [])
        return entries

    # ------------------------------------------------------ Ingesta de lote

    def ingest_urls(
        self,
        urls: list[str],
        topics: list[Topic],
        *,
        author: str | None = None,
        reliability: Reliability | None = None,
        do_index: bool = True,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        """Ingiere una lista de URLs. Salta las ya registradas si `skip_existing`."""
        registry: KnowledgeRegistry = KnowledgeRegistry(self._settings.registry_path)
        existing_urls: set[str] = {s.url for s in registry.list_all() if s.url}

        ingested: list[KnowledgeSource] = []
        skipped: list[str] = []
        errors: list[tuple[str, str]] = []

        for i, url in enumerate(urls, start=1):
            _console.print(f"\n[bold cyan]── [{i}/{len(urls)}] ──[/bold cyan] {url}")
            if skip_existing and url in existing_urls:
                _console.print("  [dim]→ ya en registry, salto.[/dim]")
                skipped.append(url)
                continue
            try:
                source: KnowledgeSource = self.ingest(
                    url,
                    topics=topics,
                    author=author,
                    reliability=reliability,
                    do_index=do_index,
                )
                ingested.append(source)
                existing_urls.add(url)
            except Exception as exc:  # noqa: BLE001 — capturamos para no abortar el lote
                _console.print(f"  [red]✗ {exc}[/red]")
                errors.append((url, str(exc)))

        return {"ingested": ingested, "skipped": skipped, "errors": errors}

    # ------------------------------------------------------ Descarga

    @staticmethod
    def _download_audio(url: str, dest_dir: Path) -> tuple[Path, dict[str, Any]]:
        """Descarga el mejor stream del vídeo. Devuelve `(ruta_archivo, metadata)`.

        No aplica postprocesado: faster-whisper decodifica vía pyav cualquier
        contenedor que ffmpeg soporte (mp4, m4a, webm, mp3...). Saltarse el
        `FFmpegExtractAudio` evita los fallos de `ffprobe` al inspeccionar
        streams HLS/m4s típicos de TikTok.
        """
        # `yt_dlp` se importa perezosamente: no se carga si no se ingiere ningún vídeo.
        import yt_dlp

        ydl_opts: dict[str, Any] = {
            # `best` agarra el stream combinado típico de TikTok (mp4 con
            # vídeo+audio embebidos). `bestaudio/best` falla porque TikTok
            # rara vez ofrece un stream de audio por separado.
            "format": "best",
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}"),
            TimeElapsedColumn(),
            console=_console,
            transient=True,
        ) as progress:
            progress.add_task("Descargando audio…", total=None)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info: dict[str, Any] = ydl.extract_info(url, download=True)

        # Localiza el archivo descargado por id (extensión determinada por yt-dlp).
        video_id: str = info["id"]
        candidates: list[Path] = sorted(dest_dir.glob(f"{video_id}.*"))
        if not candidates:
            # Fallback: el primer archivo que haya.
            candidates = sorted(p for p in dest_dir.iterdir() if p.is_file())
        if not candidates:
            raise RuntimeError(
                f"yt-dlp no produjo ningún archivo en {dest_dir}. "
                "Comprueba que `ffmpeg` está instalado y que la URL es accesible."
            )
        return candidates[0], info

    # ----------------------------------------------------- Extracción a WAV

    @staticmethod
    def _extract_wav(source_path: Path, dest_dir: Path) -> Path:
        """Convierte el archivo descargado a WAV mono 16 kHz (formato preferido por Whisper).

        Convertir explícitamente con `ffmpeg` evita los fallos de pyav cuando el
        contenedor original no expone los streams de forma estándar (caso típico
        de los mp4 de TikTok).
        """
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "`ffmpeg` no está en el PATH. Instálalo con `brew install ffmpeg`."
            )

        wav_path: Path = dest_dir / "audio.wav"
        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-i", str(source_path),
            "-vn",                # ignora el stream de vídeo
            "-ac", "1",           # mono
            "-ar", "16000",       # 16 kHz (rate nativo de Whisper)
            "-acodec", "pcm_s16le",
            str(wav_path),
        ]
        result: subprocess.CompletedProcess[bytes] = subprocess.run(
            cmd, capture_output=True, check=False
        )
        if result.returncode != 0:
            stderr: str = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"ffmpeg falló al extraer audio: {stderr}")
        if not wav_path.exists():
            raise RuntimeError(f"ffmpeg no produjo {wav_path}.")
        return wav_path

    # ----------------------------------------------------- Transcripción

    def _transcribe(self, audio_path: Path) -> str:
        """Transcribe el audio a texto plano (segmentos separados por saltos de línea)."""
        model = self._lazy_whisper()

        with Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}"),
            TimeElapsedColumn(),
            console=_console,
            transient=True,
        ) as progress:
            progress.add_task("Transcribiendo audio…", total=None)
            segments_iter, _info = model.transcribe(
                str(audio_path),
                beam_size=5,
                vad_filter=True,
                language=None,  # auto-detección
            )
            # `segments_iter` es lazy: debemos consumirlo dentro del bloque.
            lines: list[str] = []
            previous_end: float = 0.0
            for seg in segments_iter:
                text: str = seg.text.strip()
                if not text:
                    continue
                # Inserta línea en blanco si hay una pausa larga (≥ 1.5 s).
                if seg.start - previous_end > 1.5 and lines:
                    lines.append("")
                lines.append(text)
                previous_end = seg.end

        return "\n".join(lines).strip()

    def _lazy_whisper(self) -> WhisperModel:
        """Carga el modelo Whisper la primera vez que se transcribe algo."""
        if self._whisper is None:
            from faster_whisper import WhisperModel

            _console.print(
                f"[dim]Cargando Whisper ({self._whisper_model_name}, "
                f"{self._whisper_compute_type})…[/dim]"
            )
            self._whisper = WhisperModel(
                self._whisper_model_name,
                device="auto",
                compute_type=self._whisper_compute_type,
            )
        return self._whisper

    # ------------------------------------------------------- Persistencia

    def _persist_transcript(
        self,
        transcript: str,
        video_meta: dict[str, Any],
        url: str,
        topics: list[Topic],
        author: str,
        reliability: Reliability,
    ) -> KnowledgeSource:
        """Escribe el .md, lo registra en `registry.json` y devuelve la `KnowledgeSource`."""
        title: str = (video_meta.get("title") or "Sin título").strip()
        video_id: str = video_meta.get("id") or ""
        slug: str = _slugify(f"{title}-{video_id}" if video_id else title)
        source_id: str = f"video-{slug}" if not slug.startswith("video-") else slug

        date_published: date | None = self._parse_yyyymmdd(video_meta.get("upload_date"))
        markdown_path: Path = self._settings.transcripts_dir / f"{source_id}.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)

        # Construye el modelo antes de escribir, así fallamos pronto si la metadata
        # de yt-dlp viola alguna validación de Pydantic.
        relative_file_path: str = str(
            markdown_path.relative_to(PROJECT_ROOT)
        )
        source: KnowledgeSource = KnowledgeSource(
            id=source_id,
            title=title,
            author=author,
            source_type=SourceType.VIDEO_TRANSCRIPT,
            topics=topics,
            reliability=reliability,
            date_published=date_published,
            url=url,
            file_path=relative_file_path,
            language="es",
            summary=None,
        )

        markdown_path.write_text(
            self._build_markdown(source, transcript, video_meta),
            encoding="utf-8",
        )

        registry: KnowledgeRegistry = KnowledgeRegistry(self._settings.registry_path)
        registry.add(source, overwrite=True)
        registry.save()

        _console.print(
            f"[green]✓[/green] Transcripción guardada en "
            f"[bold]{markdown_path.relative_to(PROJECT_ROOT)}[/bold]."
        )
        return source

    @staticmethod
    def _build_markdown(
        source: KnowledgeSource,
        transcript: str,
        video_meta: dict[str, Any],
    ) -> str:
        """Construye el contenido Markdown con front matter alineado a `KnowledgeSource`."""
        topics_csv: str = ", ".join(t.value for t in source.topics)
        date_str: str = source.date_published.isoformat() if source.date_published else ""
        uploader: str = video_meta.get("uploader") or video_meta.get("channel") or ""
        duration: int | None = video_meta.get("duration")

        front_matter: str = (
            "---\n"
            f"id: {source.id}\n"
            f"title: {source.title}\n"
            f"author: {source.author}\n"
            f"source_type: {source.source_type.value}\n"
            f"topics: [{topics_csv}]\n"
            f"reliability: {source.reliability.value}\n"
            f"language: {source.language}\n"
            f"date_published: {date_str}\n"
            f"url: {source.url or ''}\n"
            f"uploader: {uploader}\n"
            f"duration_seconds: {duration if duration is not None else ''}\n"
            "summary: \"\"\n"
            "---\n\n"
        )
        body: str = f"# {source.title}\n\n{transcript}\n"
        return front_matter + body

    @staticmethod
    def _parse_yyyymmdd(value: str | None) -> date | None:
        """Convierte `'YYYYMMDD'` (formato de yt-dlp) a `date`. Devuelve `None` si falla."""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return None


# --------------------------------------------------------------------- CLI


app: typer.Typer = typer.Typer(
    add_completion=False,
    help="Descarga, transcribe e indexa un vídeo en la base de conocimiento.",
)


@app.command()
def main(
    url: str = typer.Argument(..., help="URL del vídeo (TikTok, YouTube, etc.)."),
    topics: str = typer.Option(
        "hypertrophy",
        "--topics",
        "-t",
        help="Topics separados por coma (valores del enum Topic).",
    ),
    author: str = typer.Option(
        VideoIngester.DEFAULT_AUTHOR,
        "--author",
        "-a",
        help="Autor del contenido.",
    ),
    reliability: str = typer.Option(
        VideoIngester.DEFAULT_RELIABILITY.value,
        "--reliability",
        "-r",
        help="Fiabilidad: anecdotal | expert_opinion | peer_reviewed | meta_analysis.",
    ),
    whisper_model: str = typer.Option(
        VideoIngester.DEFAULT_WHISPER_MODEL,
        "--whisper-model",
        help="Modelo de faster-whisper (tiny, base, small, medium, large-v3).",
    ),
    no_index: bool = typer.Option(
        False, "--no-index", help="No indexar en ChromaDB tras transcribir."
    ),
) -> None:
    """Pipeline completo de ingesta de un vídeo."""
    parsed_topics: list[Topic] = [
        Topic(t.strip()) for t in topics.split(",") if t.strip()
    ]
    parsed_reliability: Reliability = Reliability(reliability)

    indexer: KnowledgeIndexer | None = None if no_index else KnowledgeIndexer()
    ingester: VideoIngester = VideoIngester(
        indexer=indexer, whisper_model=whisper_model
    )

    source: KnowledgeSource = ingester.ingest(
        url,
        topics=parsed_topics,
        author=author,
        reliability=parsed_reliability,
        do_index=not no_index,
    )

    _console.print(
        f"\n[green]✓[/green] Vídeo ingerido: [bold]{source.id}[/bold]\n"
        f"   → topics: {', '.join(t.value for t in source.topics)}\n"
        f"   → archivo: {source.file_path}\n"
        f"{'   → indexado en ChromaDB' if not no_index else '   → sin indexar (--no-index)'}"
    )


if __name__ == "__main__":
    app()
