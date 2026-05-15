"""CLI principal del sistema fitness-agents (`fitness`).

Comandos:
    fitness start    --user-id <id>   Onboarding interactivo del usuario.
    fitness checkin  --user-id <id>   Check-in bisemanal.
    fitness status   --user-id <id>   Estado actual del usuario.
"""

from __future__ import annotations

import logging

import typer
from dotenv import load_dotenv

# Carga `.env` antes de cualquier import que lea `os.environ`.
load_dotenv()

from cli.commands.checkin import checkin_command  # noqa: E402
from cli.commands.export import (  # noqa: E402
    export_mesocycle_command,
    export_nutrition_command,
    export_progress_command,
)
from cli.commands.start import start_command  # noqa: E402
from cli.commands.status import status_command  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s · %(levelname)s · %(message)s")

app: typer.Typer = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CLI principal del sistema multi-agente de nutrición y entrenamiento.",
)

app.command("start")(start_command)
app.command("checkin")(checkin_command)
app.command("status")(status_command)
app.command("export-mesocycle")(export_mesocycle_command)
app.command("export-nutrition")(export_nutrition_command)
app.command("export-progress")(export_progress_command)


if __name__ == "__main__":
    app()
