"""Subcomandos de la CLI principal `fitness`."""

from cli.commands.checkin import checkin_command
from cli.commands.start import start_command
from cli.commands.status import status_command

__all__ = ["checkin_command", "start_command", "status_command"]
