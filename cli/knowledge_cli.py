"""CLI de gestión de la base de conocimiento (`fitness-kb`).

Comandos:
    fitness-kb index-all              Indexa todo el registry.
    fitness-kb index <source_id>      Indexa una fuente concreta.
    fitness-kb search <query>         Búsqueda semántica con filtros.
    fitness-kb stats                  Muestra estadísticas del índice.
    fitness-kb ingest-video <url>     Descarga, transcribe e indexa un vídeo.
    fitness-kb list                   Lista todas las fuentes registradas.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Carga `.env` en `os.environ` para que libs externas (huggingface_hub, etc.)
# vean variables como `HF_TOKEN`. Pydantic-settings ya lee `.env` por separado
# para los campos de `Settings`, pero no propaga a `os.environ`.
load_dotenv()

from src.config.settings import get_settings
from src.knowledge.retriever import KnowledgeRetriever, RetrievedChunk
from src.knowledge.sources import (
    KnowledgeRegistry,
    KnowledgeSource,
    Reliability,
    SourceType,
    Topic,
)

if TYPE_CHECKING:
    pass

_console: Console = Console()
_logger: logging.Logger = logging.getLogger(__name__)

app: typer.Typer = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CLI de gestión de la base de conocimiento del sistema fitness-agents.",
)


# --------------------------------------------------------------- Comandos


@app.command("index-all")
def index_all() -> None:
    """Indexa todas las fuentes del `registry.json`."""
    from src.knowledge.indexer import KnowledgeIndexer

    indexer: KnowledgeIndexer = KnowledgeIndexer()
    result: dict = indexer.index_all()

    _console.print("\n[bold]Resultado:[/bold]")
    _console.print(f"  Procesadas: [green]{result['sources_processed']}[/green]")
    _console.print(f"  Falladas:   [red]{result['sources_failed']}[/red]")
    _console.print(f"  Chunks:     [cyan]{result['total_chunks']}[/cyan]")

    if result["errors"]:
        _console.print("\n[bold red]Errores:[/bold red]")
        for err in result["errors"]:
            _console.print(f"  · {err['source_id']}: {err['error']}")


@app.command("index")
def index(source_id: str = typer.Argument(..., help="ID de la fuente.")) -> None:
    """Indexa (o reindexa) una fuente concreta del registry."""
    from src.knowledge.indexer import KnowledgeIndexer

    try:
        indexer = KnowledgeIndexer()
        n: int = indexer.reindex_source(source_id)
    except KeyError as exc:
        _console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(code=1) from None
    except FileNotFoundError as exc:
        _console.print(f"[red]✗[/red] Archivo no encontrado: {exc}")
        raise typer.Exit(code=1) from None

    _console.print(f"[green]✓[/green] {source_id}: {n} chunks indexados.")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Consulta en lenguaje natural."),
    k: int = typer.Option(5, "-k", "--k", help="Número de resultados a devolver."),
    threshold: float = typer.Option(
        0.3, "--threshold", help="Umbral mínimo de similitud (0-1)."
    ),
    topic: list[str] | None = typer.Option(
        None, "--topic", "-t", help="Filtrar por topic. Repite la flag para varios."
    ),
    source_type: list[str] | None = typer.Option(
        None, "--type", help="Filtrar por tipo de fuente. Repite la flag para varios."
    ),
    reliability_min: str | None = typer.Option(
        None, "--reliability-min", help="Fiabilidad mínima."
    ),
    author: str | None = typer.Option(None, "--author", help="Filtrar por autor."),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help=(
            "Si se especifica (training|nutrition|assessment|progress), aplica "
            "el preset de topics del agente."
        ),
    ),
) -> None:
    """Búsqueda semántica rápida sobre el índice."""
    retriever: KnowledgeRetriever = KnowledgeRetriever()

    if agent is not None:
        if agent not in {"training", "nutrition", "assessment", "progress"}:
            _console.print(f"[red]✗[/red] agent inválido: {agent!r}")
            raise typer.Exit(code=1)
        # Aprovechamos retrieve_for_agent para devolver el contexto formateado.
        context: str = retriever.retrieve_for_agent(query, agent_type=agent, k=k)  # type: ignore[arg-type]
        _console.print(context)
        return

    parsed_topics: list[Topic] | None = (
        [Topic(t) for t in topic] if topic else None
    )
    parsed_types: list[SourceType] | None = (
        [SourceType(s) for s in source_type] if source_type else None
    )
    parsed_rel: Reliability | None = (
        Reliability(reliability_min) if reliability_min else None
    )

    results: list[RetrievedChunk] = retriever.retrieve(
        query=query,
        topics=parsed_topics,
        source_types=parsed_types,
        reliability_min=parsed_rel,
        author=author,
        k=k,
        score_threshold=threshold,
    )
    _print_search_results(query, results)


@app.command("stats")
def stats() -> None:
    """Muestra estadísticas de la colección ChromaDB."""
    from src.knowledge.indexer import KnowledgeIndexer

    indexer = KnowledgeIndexer()
    info: dict = indexer.get_stats()

    table: Table = Table(title="Base de conocimiento — estadísticas", show_lines=False)
    table.add_column("Métrica", style="cyan", no_wrap=True)
    table.add_column("Valor", style="white")

    table.add_row("Total chunks", str(info["total_chunks"]))
    table.add_row("Fuentes únicas", str(info["unique_sources"]))
    table.add_row("Colección", info["collection_name"])
    table.add_row("Persist dir", info["persist_dir"])
    table.add_row("Embedding model", info["embedding_model"])

    _console.print(table)

    if info["source_ids"]:
        _console.print("\n[bold]Fuentes indexadas:[/bold]")
        for sid in info["source_ids"]:
            _console.print(f"  · {sid}")


@app.command("list")
def list_sources() -> None:
    """Lista todas las fuentes del registry."""
    settings = get_settings()
    registry: KnowledgeRegistry = KnowledgeRegistry(settings.registry_path)
    sources: list[KnowledgeSource] = registry.list_all()

    if not sources:
        _console.print(
            f"[yellow]El registry está vacío ({settings.registry_path}).[/yellow]"
        )
        return

    table: Table = Table(
        title=f"{len(sources)} fuentes en el registry",
        show_lines=False,
    )
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Título")
    table.add_column("Autor", style="dim")
    table.add_column("Tipo", style="magenta")
    table.add_column("Topics", style="green")
    table.add_column("Fiabilidad", style="yellow")

    for s in sources:
        topics_text: str = ", ".join(t.value for t in s.topics[:3])
        if len(s.topics) > 3:
            topics_text += f" (+{len(s.topics) - 3})"
        table.add_row(
            s.id,
            _truncate(s.title, 40),
            _truncate(s.author, 20),
            s.source_type.value,
            topics_text,
            s.reliability.value,
        )

    _console.print(table)


@app.command("sync-registry")
def sync_registry_cmd(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Muestra los cambios sin escribir el registry."
    ),
) -> None:
    """Reconstruye/actualiza `registry.json` desde el front matter de los `.md`."""
    from src.knowledge.registry_sync import sync_registry

    result = sync_registry(dry_run=dry_run)

    _console.print(f"\n[bold]Escaneados:[/bold] {result.scanned} archivos\n")

    if result.added:
        _console.print(f"[green]+ Añadidas ({len(result.added)})[/green]")
        for sid in result.added:
            _console.print(f"    [green]+[/green] {sid}")

    if result.updated:
        _console.print(f"\n[yellow]~ Actualizadas ({len(result.updated)})[/yellow]")
        for sid in result.updated:
            _console.print(f"    [yellow]~[/yellow] {sid}")

    if result.unchanged:
        _console.print(
            f"\n[dim]= Sin cambios ({len(result.unchanged)})[/dim]"
        )

    if result.skipped:
        _console.print(f"\n[dim]Saltados ({len(result.skipped)}):[/dim]")
        for path, reason in result.skipped:
            _console.print(f"    · {path}: {reason}")

    if result.errors:
        _console.print(f"\n[red]Errores ({len(result.errors)}):[/red]")
        for path, err in result.errors:
            _console.print(f"    [red]✗[/red] {path}: {err}")

    if dry_run:
        _console.print(
            "\n[yellow]--dry-run: no se ha escrito registry.json.[/yellow]"
        )
    elif result.added or result.updated:
        _console.print("\n[green]✓[/green] registry.json actualizado.")


@app.command("list-profile")
def list_profile_cmd(
    profile_url: str = typer.Argument(
        ..., help="URL del perfil (TikTok, YouTube, etc.)."
    ),
    output: Path = typer.Option(
        Path("videos.txt"),
        "--output",
        "-o",
        help="Archivo de texto donde escribir la lista para edición.",
    ),
) -> None:
    """Lista los vídeos de un perfil y los vuelca en un archivo editable."""
    from src.knowledge.sources import KnowledgeRegistry
    from src.knowledge.video_ingest import VideoIngester

    settings = get_settings()

    with _console.status(f"[cyan]Listando vídeos de {profile_url}…[/cyan]"):
        entries = VideoIngester.list_profile_videos(profile_url)

    if not entries:
        _console.print(
            f"[yellow]No se encontraron vídeos en {profile_url}.[/yellow]"
        )
        raise typer.Exit(code=1)

    registry = KnowledgeRegistry(settings.registry_path)
    existing_urls: set[str] = {s.url for s in registry.list_all() if s.url}

    # Tabla en pantalla
    table = Table(title=f"{len(entries)} vídeos en {profile_url}", show_lines=False)
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Estado", style="green")
    table.add_column("Duración", justify="right")
    table.add_column("Título", overflow="ellipsis", max_width=70)

    for i, entry in enumerate(entries, start=1):
        url = entry.get("url") or entry.get("webpage_url") or ""
        status = "[YA]" if url in existing_urls else ""
        duration = _fmt_duration(entry.get("duration"))
        title = entry.get("title") or "(sin título)"
        table.add_row(str(i), status, duration, title)

    _console.print(table)

    # Archivo editable
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    listed_urls = {
        e.get("url") or e.get("webpage_url") or ""
        for e in entries
    }
    existing_count = len(existing_urls & listed_urls)
    lines: list[str] = [
        f"# fitness-kb — vídeos de {profile_url}",
        f"# Generado: {timestamp}",
        f"# Total: {len(entries)} vídeos ({existing_count} ya en registry)",
        "#",
        "# Edita esta lista: borra (o comenta con #) las líneas de los vídeos",
        "# que NO quieras ingerir. Después:",
        f"#     fitness-kb ingest-from-list {output} --topics hypertrophy",
        "#",
        "# Formato: <URL>  # <duración>  <título>",
        "",
    ]
    for entry in entries:
        url = entry.get("url") or entry.get("webpage_url") or ""
        if not url:
            continue
        duration = _fmt_duration(entry.get("duration"))
        title = (entry.get("title") or "(sin título)").replace("\n", " ")
        marker = "# [YA]" if url in existing_urls else "#"
        lines.append(f"{url}  {marker} {duration}  {title}")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _console.print(
        f"\n[green]✓[/green] Lista escrita en [bold]{output}[/bold]. "
        f"Edítala y ejecuta:\n"
        f"  [cyan]fitness-kb ingest-from-list {output} --topics hypertrophy[/cyan]"
    )


@app.command("ingest-from-list")
def ingest_from_list_cmd(
    list_file: Path = typer.Argument(
        ..., help="Archivo de texto con una URL por línea (ver `list-profile`)."
    ),
    topics: str = typer.Option(
        "hypertrophy",
        "--topics",
        "-t",
        help="Topics separados por coma, aplicados a TODOS los vídeos del lote.",
    ),
    author: str = typer.Option(
        "Fran Pérez Jurado", "--author", "-a", help="Autor del contenido."
    ),
    reliability: str = typer.Option(
        "expert_opinion",
        "--reliability",
        "-r",
        help="anecdotal | expert_opinion | peer_reviewed | meta_analysis.",
    ),
    whisper_model: str = typer.Option("small", "--whisper-model"),
    no_index: bool = typer.Option(False, "--no-index"),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="Saltar URLs ya presentes en el registry.",
    ),
) -> None:
    """Ingiere los vídeos cuyas URLs están en `list_file`."""
    from src.knowledge.indexer import KnowledgeIndexer
    from src.knowledge.video_ingest import VideoIngester

    if not list_file.exists():
        _console.print(f"[red]✗[/red] Archivo no encontrado: {list_file}")
        raise typer.Exit(code=1)

    urls: list[str] = _parse_url_list(list_file)
    if not urls:
        _console.print(
            f"[yellow]Sin URLs en {list_file} (¿borraste todas las líneas?).[/yellow]"
        )
        raise typer.Exit(code=1)

    parsed_topics: list[Topic] = [
        Topic(t.strip()) for t in topics.split(",") if t.strip()
    ]
    parsed_reliability: Reliability = Reliability(reliability)

    indexer = None if no_index else KnowledgeIndexer()
    ingester: VideoIngester = VideoIngester(
        indexer=indexer, whisper_model=whisper_model
    )

    _console.print(
        f"[bold]Ingestando {len(urls)} URLs[/bold] "
        f"(topics: [cyan]{', '.join(t.value for t in parsed_topics)}[/cyan])\n"
    )

    result = ingester.ingest_urls(
        urls,
        topics=parsed_topics,
        author=author,
        reliability=parsed_reliability,
        do_index=not no_index,
        skip_existing=skip_existing,
    )

    _console.print(
        f"\n[bold]Resultado:[/bold]\n"
        f"  [green]✓ Ingeridos:[/green] {len(result['ingested'])}\n"
        f"  [dim]→ Saltados:[/dim]   {len(result['skipped'])}\n"
        f"  [red]✗ Errores:[/red]   {len(result['errors'])}"
    )
    if result["errors"]:
        _console.print("\n[red]Detalle de errores:[/red]")
        for url, err in result["errors"]:
            _console.print(f"  · {url}\n    {err}")


@app.command("ingest-video")
def ingest_video(
    url: str = typer.Argument(..., help="URL del vídeo (TikTok, YouTube, etc.)."),
    topics: str = typer.Option(
        "hypertrophy",
        "--topics",
        "-t",
        help="Topics separados por coma (valores del enum Topic).",
    ),
    author: str = typer.Option(
        "Fran Pérez Jurado", "--author", "-a", help="Autor del contenido."
    ),
    reliability: str = typer.Option(
        "expert_opinion",
        "--reliability",
        "-r",
        help="anecdotal | expert_opinion | peer_reviewed | meta_analysis.",
    ),
    whisper_model: str = typer.Option(
        "small", "--whisper-model", help="tiny|base|small|medium|large-v3."
    ),
    no_index: bool = typer.Option(
        False, "--no-index", help="No indexar tras transcribir."
    ),
) -> None:
    """Descarga, transcribe y registra un vídeo. Por defecto también lo indexa."""
    from src.knowledge.indexer import KnowledgeIndexer
    from src.knowledge.video_ingest import VideoIngester

    parsed_topics: list[Topic] = [
        Topic(t.strip()) for t in topics.split(",") if t.strip()
    ]
    parsed_reliability: Reliability = Reliability(reliability)

    indexer = None if no_index else KnowledgeIndexer()
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
        f"   topics:  {', '.join(t.value for t in source.topics)}\n"
        f"   archivo: {source.file_path}\n"
        f"   {'indexado en ChromaDB' if not no_index else 'sin indexar (--no-index)'}"
    )


# --------------------------------------------------------------- Helpers


def _print_search_results(query: str, results: list[RetrievedChunk]) -> None:
    """Imprime los resultados de búsqueda con score y preview."""
    if not results:
        _console.print(
            f"[yellow]Sin resultados para[/yellow] [italic]{query!r}[/italic]."
        )
        return

    _console.print(
        f"[bold]{len(results)}[/bold] resultados para "
        f"[italic]{query!r}[/italic]:\n"
    )
    for i, chunk in enumerate(results, start=1):
        score_color: str = (
            "green" if chunk.score >= 0.7
            else "yellow" if chunk.score >= 0.5
            else "red"
        )
        _console.print(
            f"[bold]{i}.[/bold] "
            f"[{score_color}]score={chunk.score:.3f}[/{score_color}] · "
            f"[bold]{chunk.title}[/bold]"
        )
        _console.print(
            f"   [dim]{chunk.author} · {chunk.source_type.value} · "
            f"{chunk.reliability.value}[/dim]"
        )
        preview: str = chunk.content.replace("\n", " ")
        if len(preview) > 240:
            preview = preview[:240] + "…"
        _console.print(f"   {preview}\n")


def _truncate(text: str, max_len: int) -> str:
    """Recorta `text` a `max_len` con ellipsis si excede."""
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _fmt_duration(seconds: float | int | None) -> str:
    """Formatea segundos como `m:ss`. Devuelve `'?'` si falta el dato."""
    if seconds is None:
        return "?"
    total: int = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _parse_url_list(path: Path) -> list[str]:
    """Lee URLs de un archivo: una por línea, primer token. Ignora vacías y `#`."""
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line: str = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line.split()[0])
    return urls


if __name__ == "__main__":
    app()
