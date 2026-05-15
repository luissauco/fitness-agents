"""Clase base para los generadores de archivos descargables.

Cada generador concreto (Excel de mesociclo, PDF nutricional, PDF de
progreso) hereda de `FileGenerator` y convierte un modelo Pydantic en el
archivo final que consume el usuario.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import BaseModel

_logger: Final[logging.Logger] = logging.getLogger(__name__)


class FileGenerator(ABC):
    """Base común para todos los generadores de archivos."""

    output_dir: Path

    def __init__(self, output_dir: Path | str = "output") -> None:
        """Crea el directorio de salida si no existe."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def generate(self, model: BaseModel, **kwargs: object) -> Path:
        """Genera el archivo a partir del modelo y devuelve su `Path`."""
        ...

    def _build_filename(self, prefix: str, identifier: str, extension: str) -> Path:
        """Construye el nombre `{prefix}_{identifier}_{fecha}.{ext}`."""
        today: str = date.today().strftime("%Y-%m-%d")
        safe_identifier: str = identifier.replace(" ", "_")
        filename: str = f"{prefix}_{safe_identifier}_{today}.{extension}"
        path: Path = self.output_dir / filename
        _logger.debug("Archivo de salida resuelto: %s", path)
        return path
