"""Comandos `fitness export-*`: regeneran archivos sin re-ejecutar agentes."""

from __future__ import annotations

import typer
from rich.console import Console

from cli.commands.factory import build_container
from src.generators.pdf_nutrition import NutritionPDFGenerator
from src.generators.pdf_progress import ProgressPDFGenerator
from src.generators.xlsx_mesocycle import MesocycleExcelGenerator

_console: Console = Console()


def export_mesocycle_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
) -> None:
    """Regenera el Excel del mesociclo activo."""
    repos = build_container().repos
    profile = repos.user_profile.get(user_id)
    if profile is None:
        _console.print(f"[red]No hay perfil para `{user_id}`.[/red]")
        raise typer.Exit(code=1)

    mesocycle = repos.mesocycle.get_current(user_id)
    if mesocycle is None:
        _console.print("[red]No hay mesociclo activo.[/red]")
        raise typer.Exit(code=1)

    path = MesocycleExcelGenerator().generate(mesocycle, profile.personal.name)
    _console.print(f"[green]Generado:[/green] {path}")


def export_nutrition_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
) -> None:
    """Regenera el PDF del plan nutricional activo."""
    repos = build_container().repos
    profile = repos.user_profile.get(user_id)
    if profile is None:
        _console.print(f"[red]No hay perfil para `{user_id}`.[/red]")
        raise typer.Exit(code=1)

    plan = repos.nutrition_plan.get_current(user_id)
    if plan is None:
        _console.print("[red]No hay plan nutricional activo.[/red]")
        raise typer.Exit(code=1)

    path = NutritionPDFGenerator().generate(plan, profile.personal.name)
    _console.print(f"[green]Generado:[/green] {path}")


def export_progress_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
    log_id: str | None = typer.Option(
        None, "--log-id", "-l", help="ID del check-in a exportar (por defecto, el último)."
    ),
) -> None:
    """Regenera el PDF de un informe de progreso."""
    repos = build_container().repos
    profile = repos.user_profile.get(user_id)
    if profile is None:
        _console.print(f"[red]No hay perfil para `{user_id}`.[/red]")
        raise typer.Exit(code=1)

    logs = repos.progress_log.list_for_user(user_id)
    if not logs:
        _console.print("[red]No hay informes de progreso.[/red]")
        raise typer.Exit(code=1)

    if log_id is not None:
        target = next((lg for lg in logs if lg.id == log_id), None)
        if target is None:
            _console.print(f"[red]No existe el check-in `{log_id}`.[/red]")
            raise typer.Exit(code=1)
    else:
        target = max(logs, key=lambda lg: lg.period_end)

    previous = [lg for lg in logs if lg.period_end < target.period_end]
    path = ProgressPDFGenerator().generate(target, profile.personal.name, previous_logs=previous)
    _console.print(f"[green]Generado:[/green] {path}")
