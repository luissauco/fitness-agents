"""Generador del PDF del plan nutricional.

Estructura multipágina: portada, dieta de días de entreno, dieta de días
de descanso, comparativa entreno/descanso, protocolo de cheat meal (si
existe), tips e intercambiabilidad, y NEAT/cardio.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Final
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.generators.base import FileGenerator
from src.generators.styles import pdf_styles as ps
from src.models.nutrition_plan import DailyDiet, FoodItem, Meal, NutritionPlan

_logger: Final[logging.Logger] = logging.getLogger(__name__)


def _esc(text: str) -> str:
    """Escapa texto para los `Paragraph` de ReportLab."""
    return escape(str(text))


def _fmt_g(grams: float) -> str:
    """Formatea gramos sin decimal si es entero (80.0 → '80')."""
    return str(int(grams)) if grams == int(grams) else str(grams)


class NutritionPDFGenerator(FileGenerator):
    """Genera el PDF del plan nutricional a partir de un `NutritionPlan`."""

    def generate(self, plan: NutritionPlan, user_name: str) -> Path:  # type: ignore[override]
        """Genera el PDF y devuelve su `Path`."""
        filename: Path = self._build_filename(
            prefix="Plan_Nutricional", identifier=user_name, extension="pdf"
        )

        doc = SimpleDocTemplate(
            str(filename),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            title=f"Plan Nutricional - {user_name}",
        )

        story: list = []
        story.extend(self._build_cover(plan, user_name))
        story.append(PageBreak())
        story.extend(self._build_daily_diet(plan.training_day_diet, "DÍAS DE ENTRENO"))
        story.append(PageBreak())
        story.extend(self._build_daily_diet(plan.rest_day_diet, "DÍAS DE DESCANSO"))
        story.append(PageBreak())
        story.extend(self._build_comparison(plan))
        if plan.cheat_meal_protocol is not None:
            story.append(PageBreak())
            story.extend(self._build_cheat_protocol(plan))
        story.append(PageBreak())
        story.extend(self._build_tips(plan))
        story.append(PageBreak())
        story.extend(self._build_neat_cardio(plan))

        self._user_name = user_name
        doc.build(story, onFirstPage=self._footer_only, onLaterPages=self._header_footer)
        _logger.info("PDF nutricional generado: %s", filename)
        return filename

    # --------------------------------- páginas --------------------------------

    def _build_cover(self, plan: NutritionPlan, user_name: str) -> list:
        """Portada con título y datos del plan."""
        items: list = [Spacer(1, 4 * cm), Paragraph("PROGRAMA NUTRICIONAL", ps.title_style())]
        items.append(Spacer(1, 1 * cm))
        info = ps.cover_info_style()
        items.append(Paragraph(f"<b>{_esc(user_name)}</b>", info))
        items.append(Paragraph(f"Objetivo: {_esc(plan.objective)}", info))
        items.append(Paragraph(f"Fase: {_esc(plan.phase)}", info))
        items.append(Paragraph(f"Duración: {_esc(plan.duration)}", info))
        items.append(Paragraph(f"Inicio: {plan.start_date.isoformat()}", info))
        items.append(Spacer(1, 5 * cm))
        items.append(
            Paragraph(
                "Este plan no sustituye al consejo médico profesional.",
                ps.small_style(),
            )
        )
        return items

    def _build_daily_diet(self, diet: DailyDiet, title: str) -> list:
        """Página de dieta para un tipo de día (entreno o descanso)."""
        items: list = [Paragraph(title, ps.page_title_style())]
        items.append(self._macro_table(diet))
        items.append(Spacer(1, 0.5 * cm))

        if diet.supplements:
            items.append(
                Paragraph(
                    f"<b>SUPLEMENTACIÓN:</b> {_esc(', '.join(diet.supplements))}",
                    ps.body_style(),
                )
            )
            items.append(Spacer(1, 0.3 * cm))

        for meal in diet.meals:
            items.extend(self._meal_block(meal))
        return items

    def _build_comparison(self, plan: NutritionPlan) -> list:
        """Comparativa de macros entre día de entreno y descanso."""
        t = plan.training_day_diet.macros
        r = plan.rest_day_diet.macros
        rows = [
            ["", "Entreno", "Descanso"],
            ["Kcal", str(t.calories), str(r.calories)],
            ["Proteína (g)", str(t.protein_g), str(r.protein_g)],
            ["Hidratos (g)", str(t.carbs_g), str(r.carbs_g)],
            ["Grasas (g)", str(t.fat_g), str(r.fat_g)],
        ]
        table = Table(rows, colWidths=[5 * cm, 4 * cm, 4 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ps.ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), ps.WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, ps.SECONDARY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ps.WHITE, ps.WHITE]),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        diff = plan.calorie_difference
        return [
            Paragraph("DISTRIBUCIÓN ENTRENO / DESCANSO", ps.page_title_style()),
            table,
            Spacer(1, 0.5 * cm),
            Paragraph(
                f"Diferencia: <b>{diff:+d} kcal</b> entre día de entreno y descanso.",
                ps.body_style(),
            ),
            Spacer(1, 0.3 * cm),
            Paragraph(
                "La distribución semanal de días de entreno/descanso sigue el "
                "esquema del mesociclo (ver Excel de entrenamiento).",
                ps.small_style(),
            ),
        ]

    def _build_cheat_protocol(self, plan: NutritionPlan) -> list:
        """Página del protocolo de comida libre."""
        protocol = plan.cheat_meal_protocol
        assert protocol is not None  # garantizado por el caller
        items: list = [Paragraph("PROTOCOLO DE COMIDA LIBRE", ps.page_title_style())]
        items.append(Paragraph("Estrategia general", ps.section_style()))
        items.append(Paragraph(_esc(protocol.strategy), ps.body_style()))
        if protocol.pre_cheat_tips:
            items.append(Paragraph("Antes del cheat", ps.section_style()))
            items.extend(self._bullets(protocol.pre_cheat_tips))
        if protocol.day_structure:
            items.append(Paragraph("Estructura del día", ps.section_style()))
            items.extend(self._bullets(protocol.day_structure, numbered=True))
        items.append(Paragraph("Frecuencia", ps.section_style()))
        items.append(Paragraph(_esc(protocol.frequency), ps.body_style()))
        return items

    def _build_tips(self, plan: NutritionPlan) -> list:
        """Página de tips generales y reglas de intercambiabilidad."""
        tips = plan.general_tips
        rules = plan.interchange_rules
        items: list = [Paragraph("TIPS GENERALES", ps.page_title_style())]
        items.extend(self._bullets(tips.tips))

        items.append(Paragraph("Bebidas y condimentos", ps.section_style()))
        if tips.allowed_drinks:
            items.append(
                Paragraph(
                    f"Bebidas permitidas: {_esc(', '.join(tips.allowed_drinks))}",
                    ps.body_style(),
                )
            )
        items.append(Paragraph(f"Salsas: {_esc(tips.sauce_rule)}", ps.body_style()))
        items.append(Paragraph(f"Condimentos: {_esc(tips.seasoning_notes)}", ps.body_style()))

        items.append(Paragraph("REGLAS DE INTERCAMBIABILIDAD", ps.section_style()))
        if rules.carb_sources:
            rows = [["Referencia", "Equivalente"]] + [
                [_esc(k), _esc(v)] for k, v in rules.carb_sources.items()
            ]
            table = Table(rows, colWidths=[7 * cm, 7 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), ps.ACCENT),
                        ("TEXTCOLOR", (0, 0), (-1, 0), ps.WHITE),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, ps.SECONDARY),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            items.append(table)
            items.append(Spacer(1, 0.3 * cm))
        if rules.protein_sources:
            items.append(
                Paragraph(
                    f"<b>Proteínas intercambiables (a igualdad de gramos):</b> "
                    f"{_esc(', '.join(rules.protein_sources))}",
                    ps.body_style(),
                )
            )
        items.append(Paragraph(f"<b>Verduras:</b> {_esc(rules.vegetable_rule)}", ps.body_style()))
        items.append(Paragraph(f"<b>Frutas:</b> {_esc(rules.fruit_rule)}", ps.body_style()))
        for note in rules.notes:
            items.append(Paragraph(f"• {_esc(note)}", ps.body_style()))
        return items

    def _build_neat_cardio(self, plan: NutritionPlan) -> list:
        """Página de NEAT y cardio."""
        return [
            Paragraph("CARDIO Y NEAT", ps.page_title_style()),
            Paragraph(
                "El NEAT (actividad diaria no deportiva: pasos, recados, escaleras) "
                "es clave para el gasto calórico sostenible. El cardio LISS "
                "(baja intensidad, larga duración) complementa sin interferir "
                "en la recuperación.",
                ps.body_style(),
            ),
            Spacer(1, 0.4 * cm),
            Paragraph("Pautas del plan", ps.section_style()),
            Paragraph(_esc(plan.neat_cardio_notes), ps.body_style()),
        ]

    # --------------------------------- helpers --------------------------------

    def _macro_table(self, diet: DailyDiet) -> Table:
        """Tabla horizontal con kcal y macros del día."""
        m = diet.macros
        data = [
            [f"{m.calories} KCAL", f"{m.protein_g}g PROT", f"{m.carbs_g}g HC", f"{m.fat_g}g GRASA"]
        ]
        table = Table(data, colWidths=[4 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), ps.ACCENT),
                    ("BACKGROUND", (1, 0), (1, 0), ps.PRIMARY),
                    ("BACKGROUND", (2, 0), (2, 0), ps.PRIMARY),
                    ("BACKGROUND", (3, 0), (3, 0), ps.PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), ps.WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return table

    def _meal_block(self, meal: Meal) -> list:
        """Bloque de una comida con sus alimentos."""
        header: str = meal.name
        if meal.time_suggestion:
            header += f"  ({_esc(meal.time_suggestion)})"
        if meal.is_intra_workout:
            header += "  [INTRA-ENTRENO]"
        items: list = [Paragraph(_esc(header), ps.section_style())]
        for food in meal.foods:
            items.append(Paragraph(self._food_line(food), ps.body_style()))
            if food.preparation_notes:
                items.append(Paragraph(_esc(food.preparation_notes), ps.small_style()))
        if meal.notes:
            items.append(Paragraph(_esc(meal.notes), ps.small_style()))
        items.append(Spacer(1, 0.2 * cm))
        return items

    def _food_line(self, food: FoodItem) -> str:
        """Construye la línea de un alimento con sus alternativas."""
        base: str = f"• {_fmt_g(food.amount_g)}gr de {_esc(food.name)}"
        if food.alternative_amounts:
            base += "  /  " + "  /  ".join(_esc(a) for a in food.alternative_amounts)
        elif food.alternatives:
            base += f" (alt: {_esc(' / '.join(food.alternatives))})"
        if food.is_optional:
            base += " <i>(opcional)</i>"
        return base

    def _bullets(self, items: list[str], *, numbered: bool = False) -> list:
        """Lista de párrafos con viñetas o numerada."""
        out: list = []
        for i, text in enumerate(items, start=1):
            prefix: str = f"{i}. " if numbered else "• "
            out.append(Paragraph(f"{prefix}{_esc(text)}", ps.body_style()))
        return out

    # ------------------------------ header/footer -----------------------------

    def _footer_only(self, canvas, doc) -> None:  # noqa: ANN001
        """Pie de página de la portada (sin cabecera)."""
        self._draw_footer(canvas, doc)

    def _header_footer(self, canvas, doc) -> None:  # noqa: ANN001
        """Cabecera (nombre + página) y pie en páginas interiores."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ps.SECONDARY)
        canvas.drawString(2 * cm, A4[1] - 1.2 * cm, getattr(self, "_user_name", ""))
        canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.2 * cm, f"Pág. {doc.page}")
        canvas.restoreState()
        self._draw_footer(canvas, doc)

    @staticmethod
    def _draw_footer(canvas, doc) -> None:  # noqa: ANN001
        """Pie común a todas las páginas."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ps.SECONDARY)
        canvas.drawCentredString(
            A4[0] / 2,
            1.2 * cm,
            f"Plan generado el {date.today().isoformat()}",
        )
        canvas.restoreState()
