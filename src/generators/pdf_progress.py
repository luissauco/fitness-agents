"""Generador del PDF de informe de progreso bisemanal.

Seis páginas: resumen ejecutivo, composición corporal (con gráfico de
peso si hay histórico), entrenamiento, nutrición, sensaciones subjetivas
y decisión del coach.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Final
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")  # backend sin display, debe fijarse antes de pyplot.

import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.generators.base import FileGenerator  # noqa: E402
from src.generators.styles import pdf_styles as ps  # noqa: E402
from src.generators.styles.colors import (  # noqa: E402
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_WARNING,
)
from src.models.progress_log import ProgressLog  # noqa: E402

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Acción del agente → texto legible en español.
_ACTION_LABELS: Final[dict[str, str]] = {
    "continue": "Mantener el plan actual",
    "adjust_calories": "Ajustar calorías",
    "adjust_macros": "Ajustar macronutrientes",
    "adjust_volume": "Ajustar volumen de entrenamiento",
    "early_deload": "Adelantar descarga",
    "change_phase": "Cambiar de fase",
    "new_mesocycle": "Iniciar nuevo mesociclo",
}

_TREND_LABELS: Final[dict[str, str]] = {
    "losing": "Bajando",
    "stable": "Estable",
    "gaining": "Subiendo",
}

# Métricas corporales a mostrar (atributo → etiqueta).
_MEASURE_FIELDS: Final[list[tuple[str, str]]] = [
    ("weight_kg", "Peso (kg)"),
    ("waist_cm", "Cintura (cm)"),
    ("hip_cm", "Cadera (cm)"),
    ("chest_cm", "Pecho (cm)"),
    ("arm_left_cm", "Brazo izq. (cm)"),
    ("arm_right_cm", "Brazo der. (cm)"),
    ("thigh_left_cm", "Muslo izq. (cm)"),
    ("thigh_right_cm", "Muslo der. (cm)"),
    ("calf_left_cm", "Gemelo izq. (cm)"),
    ("calf_right_cm", "Gemelo der. (cm)"),
    ("neck_cm", "Cuello (cm)"),
    ("shoulder_cm", "Hombros (cm)"),
]

_SUBJECTIVE_FIELDS: Final[list[tuple[str, str]]] = [
    ("energy_level", "Energía"),
    ("sleep_quality", "Sueño"),
    ("hunger_level", "Hambre"),
    ("motivation", "Motivación"),
    ("stress_level", "Estrés"),
    ("soreness", "DOMS"),
    ("mood", "Estado de ánimo"),
]


def _esc(text: object) -> str:
    """Escapa texto para los `Paragraph` de ReportLab."""
    return escape(str(text))


class ProgressPDFGenerator(FileGenerator):
    """Genera el PDF de progreso a partir de un `ProgressLog`."""

    def generate(  # type: ignore[override]
        self,
        log: ProgressLog,
        user_name: str,
        previous_logs: list[ProgressLog] | None = None,
    ) -> Path:
        """Genera el PDF de progreso y devuelve su `Path`."""
        previous: list[ProgressLog] = sorted(previous_logs or [], key=lambda lg: lg.period_end)
        filename: Path = self._build_filename(
            prefix="Informe_Progreso", identifier=user_name, extension="pdf"
        )

        doc = SimpleDocTemplate(
            str(filename),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            title=f"Informe de Progreso - {user_name}",
        )

        story: list = []
        story.extend(self._build_executive_summary(log))
        story.append(PageBreak())
        story.extend(self._build_body_composition(log, previous))
        story.append(PageBreak())
        story.extend(self._build_training_section(log))
        story.append(PageBreak())
        story.extend(self._build_nutrition_section(log))
        story.append(PageBreak())
        story.extend(self._build_subjective_section(log))
        story.append(PageBreak())
        story.extend(self._build_decision_section(log))

        self._user_name = user_name
        doc.build(story, onFirstPage=self._footer_only, onLaterPages=self._header_footer)
        _logger.info("PDF de progreso generado: %s", filename)
        return filename

    # --------------------------------- páginas --------------------------------

    def _build_executive_summary(self, log: ProgressLog) -> list:
        """Página 1: resumen ejecutivo con caja de tendencia coloreada."""
        color, label = self._overall(log)
        box = Table(
            [[Paragraph(f"<b>TENDENCIA: {label}</b>", ps.cover_info_style())]],
            colWidths=[14 * cm],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), color),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        return [
            Paragraph("RESUMEN EJECUTIVO", ps.page_title_style()),
            Paragraph(
                f"Período: {log.period_start.isoformat()} → {log.period_end.isoformat()}",
                ps.body_style(),
            ),
            Paragraph(f"Microciclo completado: {log.microcycle_number}", ps.body_style()),
            Spacer(1, 0.5 * cm),
            box,
            Spacer(1, 0.6 * cm),
            Paragraph(_esc(log.report_summary), ps.body_style()),
        ]

    def _build_body_composition(self, log: ProgressLog, previous: list[ProgressLog]) -> list:
        """Página 2: tabla de medidas y gráfico de peso si hay histórico."""
        items: list = [Paragraph("COMPOSICIÓN CORPORAL", ps.page_title_style())]

        prev_m = previous[-1].measurements if previous else None
        rows: list[list[str]] = [["Métrica", "Actual", "Anterior", "Cambio"]]
        for attr, label in _MEASURE_FIELDS:
            actual = getattr(log.measurements, attr)
            if actual is None:
                continue
            prev_val = getattr(prev_m, attr) if prev_m else None
            if prev_val is None:
                rows.append([label, f"{actual:g}", "—", "—"])
            else:
                delta = actual - prev_val
                rows.append([label, f"{actual:g}", f"{prev_val:g}", f"{delta:+.1f}"])

        table = Table(rows, colWidths=[5 * cm, 3 * cm, 3 * cm, 3 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ps.ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), ps.WHITE),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, ps.SECONDARY),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        items.append(table)

        chart = self._weight_chart(log, previous)
        if chart is not None:
            items.append(Spacer(1, 0.6 * cm))
            items.append(Paragraph("Evolución del peso", ps.section_style()))
            items.append(Image(chart, width=15 * cm, height=8 * cm))
        else:
            items.append(Spacer(1, 0.4 * cm))
            items.append(
                Paragraph(
                    f"Peso medio del período: <b>{log.weight.average:g} kg</b> "
                    f"(tendencia: {_TREND_LABELS[log.weight.trend]}).",
                    ps.body_style(),
                )
            )
        return items

    def _build_training_section(self, log: ProgressLog) -> list:
        """Página 3: progresión/estancamiento/regresión y PRs."""
        tr = log.training
        items: list = [Paragraph("ENTRENAMIENTO", ps.page_title_style())]
        items.append(
            self._stat_row(
                [
                    ("PROGRESÓ", tr.exercises_progressed, COLOR_SUCCESS),
                    ("ESTANCADO", tr.exercises_stagnated, COLOR_WARNING),
                    ("REGRESÓ", tr.exercises_regressed, COLOR_DANGER),
                ]
            )
        )
        items.append(Spacer(1, 0.4 * cm))
        items.append(
            Paragraph(
                f"Ejercicios trackeados: <b>{tr.exercises_tracked}</b> · "
                f"Adherencia al volumen: <b>{tr.volume_adherence_pct:g}%</b>",
                ps.body_style(),
            )
        )
        if tr.notable_prs:
            items.append(Paragraph("Récords personales", ps.section_style()))
            for pr in tr.notable_prs:
                items.append(Paragraph(f"• {_esc(pr)}", ps.body_style()))
        if tr.problem_exercises:
            items.append(Paragraph("Ejercicios problemáticos", ps.section_style()))
            for pe in tr.problem_exercises:
                items.append(Paragraph(f"• {_esc(pe)}", ps.body_style()))
        return items

    def _build_nutrition_section(self, log: ProgressLog) -> list:
        """Página 4: adherencia nutricional y pasos."""
        n = log.nutrition
        items: list = [Paragraph("NUTRICIÓN Y ADHERENCIA", ps.page_title_style())]
        items.append(
            self._stat_row(
                [
                    ("ADHERENCIA", f"{n.adherence_pct:g}%", self._adherence_color(n.adherence_pct)),
                    ("CHEAT MEALS", n.cheat_meals_count, ps.PRIMARY),
                    ("PASOS/DÍA", log.daily_steps_avg, ps.PRIMARY),
                ]
            )
        )
        items.append(Spacer(1, 0.4 * cm))
        items.append(
            Paragraph(
                f"Comidas saltadas/día (media): <b>{n.missed_meals_avg:g}</b> · "
                f"Agua: <b>{n.water_intake_liters:g} L/día</b> · "
                f"Suplementación: <b>{'sí' if n.supplement_adherence else 'no'}</b>",
                ps.body_style(),
            )
        )
        if n.notes:
            items.append(Paragraph("Notas", ps.section_style()))
            items.append(Paragraph(_esc(n.notes), ps.body_style()))
        return items

    def _build_subjective_section(self, log: ProgressLog) -> list:
        """Página 5: sensaciones subjetivas como barras 1-10."""
        s = log.subjective
        items: list = [Paragraph("SENSACIONES SUBJETIVAS", ps.page_title_style())]
        rows: list[list[str]] = []
        for attr, label in _SUBJECTIVE_FIELDS:
            value: int = getattr(s, attr)
            bar: str = "█" * value + "░" * (10 - value)
            rows.append([label, bar, f"{value}/10"])
        table = Table(rows, colWidths=[4 * cm, 8 * cm, 2 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (1, 0), (1, -1), ps.ACCENT),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        items.append(table)
        if s.pain_or_discomfort:
            items.append(Spacer(1, 0.5 * cm))
            warn = Table(
                [
                    [
                        Paragraph(
                            f"<b>Dolor / molestia:</b> {_esc(s.pain_or_discomfort)}",
                            ps.body_style(),
                        )
                    ]
                ],
                colWidths=[14 * cm],
            )
            warn.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), ps.HexColor(COLOR_WARNING)),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            items.append(warn)
        if s.additional_notes:
            items.append(Paragraph("Notas adicionales", ps.section_style()))
            items.append(Paragraph(_esc(s.additional_notes), ps.body_style()))
        return items

    def _build_decision_section(self, log: ProgressLog) -> list:
        """Página 6: decisión del coach y próximo check-in."""
        d = log.decision
        action_label: str = _ACTION_LABELS.get(d.action, d.action)
        box = Table(
            [[Paragraph(f"<b>{_esc(action_label)}</b>", ps.cover_info_style())]],
            colWidths=[14 * cm],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), ps.ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, -1), ps.WHITE),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        items: list = [
            Paragraph("DECISIÓN DEL COACH", ps.page_title_style()),
            box,
            Spacer(1, 0.5 * cm),
            Paragraph("Justificación", ps.section_style()),
            Paragraph(_esc(d.reasoning), ps.body_style()),
        ]
        if d.details:
            items.append(Paragraph("Detalles del ajuste", ps.section_style()))
            rows = [[_esc(k), _esc(v)] for k, v in d.details.items()]
            table = Table(rows, colWidths=[7 * cm, 7 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, ps.SECONDARY),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            items.append(table)
        next_checkin = log.date + timedelta(days=14)
        items.append(Spacer(1, 0.5 * cm))
        items.append(
            Paragraph(f"<b>Próximo check-in:</b> {next_checkin.isoformat()}", ps.body_style())
        )
        return items

    # --------------------------------- helpers --------------------------------

    def _stat_row(self, stats: list[tuple[str, object, object]]) -> Table:
        """Fila de cajas grandes con etiqueta y valor."""
        labels = [
            Paragraph(f"<b>{_esc(s[0])}</b><br/>{_esc(s[1])}", ps.cover_info_style()) for s in stats
        ]
        table = Table([labels], colWidths=[4.6 * cm] * len(stats))
        style: list = [
            ("TEXTCOLOR", (0, 0), (-1, -1), ps.WHITE),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]
        for i, s in enumerate(stats):
            color = s[2] if not isinstance(s[2], str) else ps.HexColor(s[2])
            style.append(("BACKGROUND", (i, 0), (i, 0), color))
        table.setStyle(TableStyle(style))
        return table

    def _weight_chart(self, log: ProgressLog, previous: list[ProgressLog]) -> BytesIO | None:
        """Genera el gráfico de peso (PNG en memoria) o None si no hay histórico."""
        series: list[tuple[str, float]] = [
            (lg.period_end.isoformat(), lg.weight.average) for lg in previous
        ]
        series.append((log.period_end.isoformat(), log.weight.average))
        if len(series) < 2:
            return None

        labels = [s[0] for s in series]
        values = [s[1] for s in series]

        fig, ax = plt.subplots(figsize=(7.5, 4))
        ax.plot(labels, values, marker="o", color="#EF9F27", linewidth=2)
        ax.set_ylabel("Peso (kg)")
        ax.grid(True, linestyle=":", alpha=0.4)
        fig.autofmt_xdate(rotation=30)
        fig.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        buf.seek(0)
        return buf

    @staticmethod
    def _overall(log: ProgressLog) -> tuple[object, str]:
        """Heurística de tendencia global → (color ReportLab, etiqueta)."""
        tr = log.training
        if tr.exercises_regressed > tr.exercises_progressed or log.nutrition.adherence_pct < 60:
            return ps.HexColor(COLOR_DANGER), "NEGATIVA"
        if tr.exercises_stagnated > tr.exercises_progressed or log.nutrition.adherence_pct < 80:
            return ps.HexColor(COLOR_WARNING), "ESTABLE"
        return ps.HexColor(COLOR_SUCCESS), "POSITIVA"

    @staticmethod
    def _adherence_color(pct: float) -> object:
        """Color según el % de adherencia."""
        if pct >= 85:
            return ps.HexColor(COLOR_SUCCESS)
        if pct >= 65:
            return ps.HexColor(COLOR_WARNING)
        return ps.HexColor(COLOR_DANGER)

    # ------------------------------ header/footer -----------------------------

    def _footer_only(self, canvas, doc) -> None:  # noqa: ANN001
        """Pie de la primera página (sin cabecera)."""
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
        from datetime import date

        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ps.SECONDARY)
        canvas.drawCentredString(
            A4[0] / 2, 1.2 * cm, f"Informe generado el {date.today().isoformat()}"
        )
        canvas.restoreState()
