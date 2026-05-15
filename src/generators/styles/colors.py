"""Paleta de colores del sistema, compartida por Excel y PDF.

Los valores se definen como hex con almohadilla (formato que acepta
ReportLab). Para openpyxl usa `argb()` que devuelve el hex de 8 dígitos
sin almohadilla.
"""

from __future__ import annotations

# Colores principales
COLOR_PRIMARY = "#1A1A1A"  # negro suave para texto principal
COLOR_SECONDARY = "#666666"  # gris medio para texto secundario
COLOR_ACCENT = "#D85A30"  # coral para destacados

# Colores semánticos
COLOR_SUCCESS = "#1D9E75"  # verde para progresión positiva
COLOR_WARNING = "#EF9F27"  # amber para estancamiento
COLOR_DANGER = "#E24B4A"  # rojo para regresión
COLOR_INFO = "#378ADD"  # azul para información

# Fondos
BG_LIGHT = "#FAFAF7"  # fondo de tablas
BG_HEADER = "#2C2C2A"  # fondo de cabeceras
BG_REST = "#F1EFE8"  # fondo días de descanso
BG_DELOAD = "#FAEEDA"  # fondo semana descarga
BG_MICROCYCLE_ODD = "#FFFFFF"
BG_MICROCYCLE_EVEN = "#F8F8F5"  # alternancia en columnas micros

# Microciclos por color (gradiente de progresión; último = descarga)
MICROCYCLE_COLORS = [
    "#E6F1FB",  # azul claro - micro 1
    "#B5D4F4",  # azul medio - micro 2
    "#85B7EB",  # azul fuerte - micro 3
    "#378ADD",  # azul más fuerte - micro 4
    "#FAEEDA",  # amber claro - descarga
]

# Texto blanco para cabeceras oscuras
COLOR_WHITE = "#FFFFFF"


def argb(hex_color: str) -> str:
    """Convierte `#RRGGBB` al `AARRGGBB` opaco que espera openpyxl."""
    cleaned: str = hex_color.lstrip("#").upper()
    if len(cleaned) != 6:
        raise ValueError(f"Color hex inválido para openpyxl: {hex_color!r}")
    return f"FF{cleaned}"


def microcycle_color(index: int, total: int, *, is_deload: bool) -> str:
    """Devuelve el color de fondo para la columna de un microciclo.

    `index` es 0-based. La descarga usa siempre el último color de la
    paleta; el resto se reparte sobre los colores no-descarga.
    """
    if is_deload:
        return MICROCYCLE_COLORS[-1]
    non_deload: list[str] = MICROCYCLE_COLORS[:-1]
    return non_deload[min(index, len(non_deload) - 1)]
