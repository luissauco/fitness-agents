"""Comando `fitness status`: resumen del estado actual de un usuario."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cli.commands.factory import build_container

_console: Console = Console()


def status_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
) -> None:
    """Muestra perfil, mesociclo activo y próximo check-in del usuario."""
    container = build_container()
    repos = container.repos

    profile = repos.user_profile.get(user_id)
    if profile is None:
        _console.print(f"[red]No hay perfil para `{user_id}`.[/red]")
        raise typer.Exit(code=1)

    mesocycle = repos.mesocycle.get_current(user_id)
    plan = repos.nutrition_plan.get_current(user_id)
    assessment = repos.body_assessment.get_latest(user_id)
    logs = repos.progress_log.list_for_user(user_id)

    table = Table(title=f"Estado de `{user_id}`", show_header=False)
    table.add_column("Clave", style="cyan", no_wrap=True)
    table.add_column("Valor")

    table.add_row("Nombre", profile.personal.name)
    table.add_row("Edad / sexo", f"{profile.personal.age} · {profile.personal.sex}")
    table.add_row(
        "Altura / peso",
        f"{profile.personal.height_cm} cm · {profile.personal.weight_kg} kg",
    )
    table.add_row("Objetivo", profile.goals.primary_goal)

    if assessment is not None:
        table.add_row("Última evaluación", assessment.date.isoformat())
        table.add_row("Fase recomendada", assessment.phase_recommendation.recommended_phase)
        table.add_row("TDEE estimado", f"{assessment.metabolic.tdee:.0f} kcal/día")

    if mesocycle is not None:
        completed = len(logs)
        total = len(mesocycle.microcycles)
        table.add_row("Mesociclo", mesocycle.name)
        table.add_row(
            "Microciclo activo",
            f"{min(completed + 1, total)}/{total} ({mesocycle.split_type})",
        )
    else:
        table.add_row("Mesociclo", "—")

    if plan is not None:
        table.add_row("Plan nutricional", plan.name)
        table.add_row("Fase nutricional", plan.phase)
    else:
        table.add_row("Plan nutricional", "—")

    if logs:
        last = logs[0]
        table.add_row("Último check-in", last.date.isoformat())
        table.add_row("Última decisión", last.decision.action)
    else:
        table.add_row("Último check-in", "—")

    _console.print(table)

    # Archivos generados para este usuario (en output/).
    safe_name: str = profile.personal.name.replace(" ", "_")
    output_dir: Path = Path("output")
    files: list[Path] = (
        sorted(p for p in output_dir.glob(f"*_{safe_name}_*") if p.is_file())
        if output_dir.is_dir()
        else []
    )
    if files:
        _console.print("\n[bold]Archivos generados:[/bold]")
        for f in files:
            _console.print(f"  · {f}")
    _console.print(
        "\n[dim]Re-exportar: fitness export-mesocycle | export-nutrition | "
        "export-progress --user-id "
        f"{user_id}[/dim]"
    )
