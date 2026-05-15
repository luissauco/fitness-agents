"""Estilos ReportLab reutilizables para los PDF (nutrición y progreso)."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle

from src.generators.styles.colors import (
    COLOR_ACCENT,
    COLOR_PRIMARY,
    COLOR_SECONDARY,
)

_PRIMARY: Color = HexColor(COLOR_PRIMARY)
_SECONDARY: Color = HexColor(COLOR_SECONDARY)
_ACCENT: Color = HexColor(COLOR_ACCENT)


def title_style() -> ParagraphStyle:
    """Título de portada (grande, centrado)."""
    return ParagraphStyle(
        "Title",
        fontName="Helvetica-Bold",
        fontSize=26,
        leading=32,
        alignment=TA_CENTER,
        textColor=_PRIMARY,
        spaceAfter=24,
    )


def page_title_style() -> ParagraphStyle:
    """Título de página interior (color accent)."""
    return ParagraphStyle(
        "PageTitle",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=_ACCENT,
        spaceAfter=14,
    )


def section_style() -> ParagraphStyle:
    """Sub-cabecera de sección."""
    return ParagraphStyle(
        "Section",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=_PRIMARY,
        spaceBefore=12,
        spaceAfter=6,
    )


def body_style() -> ParagraphStyle:
    """Cuerpo de texto."""
    return ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=_PRIMARY,
        alignment=TA_LEFT,
        spaceAfter=4,
    )


def small_style() -> ParagraphStyle:
    """Texto pequeño (notas de preparación, disclaimers)."""
    return ParagraphStyle(
        "Small",
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=_SECONDARY,
        spaceAfter=2,
    )


def cover_info_style() -> ParagraphStyle:
    """Bloque de información de la portada (centrado)."""
    return ParagraphStyle(
        "CoverInfo",
        fontName="Helvetica",
        fontSize=13,
        leading=20,
        alignment=TA_CENTER,
        textColor=_PRIMARY,
        spaceAfter=6,
    )


# Reexport para los generadores.
ACCENT = _ACCENT
PRIMARY = _PRIMARY
SECONDARY = _SECONDARY
WHITE = colors.white
