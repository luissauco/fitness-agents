"""Comando `fitness start`: onboarding interactivo de un usuario nuevo.

Bucle conversacional sobre el `IntakeAgent`. Cuando el cuestionario termina,
el grafo continúa automáticamente con `assessment → training → nutrition →
schedule_checkin` en la misma invocación. Al final, persiste los artefactos en
SQLite vía los repositorios.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer
from rich.console import Console

from cli.commands.factory import Container, build_container, persist_artifacts
from src.graph.state import FitnessState, initial_state
from src.graph.workflow import build_workflow

_console: Console = Console()


def start_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Reinicia el onboarding aunque ya exista perfil."
    ),
) -> None:
    """Inicia el onboarding interactivo del usuario."""
    asyncio.run(_run_start(user_id=user_id, force=force))


async def _run_start(*, user_id: str, force: bool) -> None:
    container: Container = build_container()
    if not force and container.repos.user_profile.get(user_id) is not None:
        _console.print(
            f"[yellow]Ya existe perfil para `{user_id}`.[/yellow] "
            "Usa `--force` para reiniciar el onboarding."
        )
        raise typer.Exit(code=1)

    workflow = build_workflow(container.bundle)
    state: FitnessState = initial_state(user_id)

    _console.print(
        f"[bold cyan]Iniciando onboarding para `{user_id}`.[/bold cyan] "
        "Escribe `salir` para abortar."
    )

    # Primer turno: el agente abre la conversación sin input previo del usuario.
    state = await workflow.ainvoke(state)
    _print_assistant(state)

    while state.get("current_phase") == "onboarding":
        action: str | None = state.get("pending_action")
        update: dict[str, Any]
        if action == "awaiting_image":
            raw: str = typer.prompt("Adjunta rutas a las imágenes (separadas por coma)", default="")
            paths: list[str] = [p.strip() for p in raw.split(",") if p.strip()]
            if not paths:
                _console.print("[yellow]Sin imágenes. Reintenta.[/yellow]")
                continue
            update = {"pending_user_input": "", "pending_user_images": paths}
        else:
            text: str = typer.prompt("Tú")
            if text.strip().lower() in {"salir", "exit", "quit"}:
                _console.print("[yellow]Onboarding abortado.[/yellow]")
                raise typer.Exit(code=1)
            update = {"pending_user_input": text, "pending_user_images": None}

        state = await workflow.ainvoke({**state, **update})
        _print_assistant(state)

    # Cuestionario terminado: el grafo ha corrido el resto de agentes en cadena.
    saved: list[str] = persist_artifacts(state, container.repos)
    _console.print(
        f"\n[bold green]Onboarding completo.[/bold green] "
        f"Fase actual: [cyan]{state.get('current_phase')}[/cyan]. "
        f"Persistido: {', '.join(saved) if saved else '—'}."
    )
    if files := state.get("generated_files"):
        _console.print("[bold]Archivos generados:[/bold]")
        for f in files:
            _console.print(f"  · {f}")
    if errors := state.get("errors"):
        _console.print("[bold red]Errores:[/bold red]")
        for e in errors:
            _console.print(f"  · {e}")


def _print_assistant(state: FitnessState) -> None:
    """Imprime el último mensaje del asistente desde la sesión de intake."""
    session = state.get("intake_session")
    if session is None or not session.conversation_history:
        return
    last: dict[str, Any] = session.conversation_history[-1]
    if last.get("role") != "assistant":
        return
    _console.print(f"\n[bold cyan]Asistente:[/bold cyan] {last.get('content', '')}")
