"""Comando `fitness checkin`: check-in bisemanal del usuario.

Carga el perfil/mesociclo/plan/logs previos desde SQLite, recoge los datos del
periodo en terminal y delega al `ProgressAgent` vía el grafo. Tras la decisión,
si el grafo regenera mesociclo o plan, persiste los nuevos artefactos.
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from cli.commands.factory import Container, build_container, persist_artifacts
from src.graph.state import FitnessState, initial_state
from src.graph.workflow import build_workflow
from src.models.body_assessment import BodyMeasurements
from src.models.checkin_input import CheckinInput
from src.models.progress_log import SubjectiveFeedback

_console: Console = Console()


def checkin_command(
    user_id: str = typer.Option(..., "--user-id", "-u", help="Identificador del usuario."),
) -> None:
    """Inicia el check-in bisemanal del usuario."""
    asyncio.run(_run_checkin(user_id=user_id))


async def _run_checkin(*, user_id: str) -> None:
    container: Container = build_container()
    repos = container.repos

    profile = repos.user_profile.get(user_id)
    mesocycle = repos.mesocycle.get_current(user_id)
    plan = repos.nutrition_plan.get_current(user_id)
    if profile is None or mesocycle is None or plan is None:
        _console.print("[red]Faltan artefactos previos. Ejecuta primero `fitness start`.[/red]")
        raise typer.Exit(code=1)

    assessment = repos.body_assessment.get_latest(user_id)
    previous_logs = repos.progress_log.list_for_user(user_id)
    # `previous_logs` viene en orden DESC por fecha; el agente espera ASC.
    previous_logs = list(reversed(previous_logs))

    _console.print(f"[bold cyan]Check-in para `{user_id}`[/bold cyan]")
    checkin_data: CheckinInput = _prompt_checkin()

    state: FitnessState = initial_state(user_id)
    state.update(
        {
            "current_phase": "checkin",
            "user_profile": profile,
            "body_assessment": assessment,
            "current_mesocycle": mesocycle,
            "current_nutrition_plan": plan,
            "current_microcycle_index": len(previous_logs),  # microciclos completados
            "progress_logs": previous_logs,
            "pending_checkin_data": checkin_data,
        }
    )

    workflow = build_workflow(container.bundle)
    final_state = await workflow.ainvoke(state)

    saved: list[str] = persist_artifacts(final_state, repos)
    new_logs = final_state.get("progress_logs") or []
    decision = new_logs[-1].decision if new_logs else None
    _console.print(
        f"\n[bold green]Check-in completo.[/bold green] "
        f"Fase: [cyan]{final_state.get('current_phase')}[/cyan]. "
        f"Persistido: {', '.join(saved) if saved else '—'}."
    )
    if decision is not None:
        _console.print(f"[bold]Decisión:[/bold] {decision.action} — {decision.reasoning}")
    if files := final_state.get("generated_files"):
        _console.print("[bold]Archivos generados:[/bold]")
        for f in files:
            _console.print(f"  · {f}")
    if errors := final_state.get("errors"):
        _console.print("[bold red]Errores:[/bold red]")
        for e in errors:
            _console.print(f"  · {e}")


def _prompt_checkin() -> CheckinInput:
    """Recoge los datos del periodo desde la terminal."""
    raw_weights: str = typer.prompt("Pesos del periodo (kg, separados por coma)")
    weights: list[float] = [float(x.strip()) for x in raw_weights.split(",") if x.strip()]
    weight_now: float = float(typer.prompt("Peso actual (kg)", default=str(weights[-1])))

    measurements = BodyMeasurements(weight_kg=weight_now)
    nutrition_pct: float = float(typer.prompt("Adherencia nutricional (0–1)", default="0.85"))
    cheats: int = int(typer.prompt("Cheat meals", default="0"))
    steps: int = int(typer.prompt("Pasos diarios (media)", default="10000"))

    _console.print("[dim]Sensaciones del periodo (1–10):[/dim]")
    subjective = SubjectiveFeedback(
        energy_level=int(typer.prompt("Energía", default="7")),
        sleep_quality=int(typer.prompt("Sueño", default="7")),
        hunger_level=int(typer.prompt("Hambre", default="5")),
        motivation=int(typer.prompt("Motivación", default="7")),
        stress_level=int(typer.prompt("Estrés", default="4")),
        soreness=int(typer.prompt("DOMS", default="4")),
        mood=int(typer.prompt("Ánimo", default="7")),
        pain_or_discomfort=typer.prompt("Dolor o molestia (vacío si no)", default="") or None,
    )
    notes: str = typer.prompt("Notas (opcional)", default="")

    return CheckinInput(
        weights=weights,
        measurements=measurements,
        nutrition_adherence_self_estimate=nutrition_pct,
        cheat_meals_count=cheats,
        daily_steps_avg=steps,
        subjective=subjective,
        user_notes=notes or None,
    )
