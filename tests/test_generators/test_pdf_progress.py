"""Tests del generador PDF de progreso."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.generators.pdf_progress import ProgressPDFGenerator
from src.models.progress_log import ProgressLog, WeightLog


def _text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() for page in reader.pages)


@pytest.fixture
def generated(tmp_path: Path, progress_log: ProgressLog) -> Path:
    gen = ProgressPDFGenerator(output_dir=tmp_path)
    return gen.generate(progress_log, user_name="Luis Sauco")


def test_file_created(generated: Path) -> None:
    assert generated.exists()
    assert generated.suffix == ".pdf"
    assert "Luis_Sauco" in generated.name


def test_six_pages(generated: Path) -> None:
    assert len(PdfReader(str(generated)).pages) == 6


def test_key_content_present(generated: Path) -> None:
    text = _text(generated)
    assert "RESUMEN EJECUTIVO" in text
    assert "COMPOSICIÓN CORPORAL" in text
    assert "ENTRENAMIENTO" in text
    assert "NUTRICIÓN Y ADHERENCIA" in text
    assert "SENSACIONES SUBJETIVAS" in text
    assert "DECISIÓN DEL COACH" in text
    # Acción "continue" → etiqueta legible.
    assert "Mantener el plan actual" in text
    # Próximo check-in = date + 14 días.
    assert "2026-06-02" in text


def test_with_previous_logs_embeds_chart(tmp_path: Path, progress_log: ProgressLog) -> None:
    prev1 = progress_log.model_copy(deep=True)
    prev1.period_end = date(2026, 4, 21)
    prev1.weight = WeightLog.from_weights([82.0, 81.7])
    prev2 = progress_log.model_copy(deep=True)
    prev2.period_end = date(2026, 5, 5)
    prev2.weight = WeightLog.from_weights([81.0, 80.6])

    gen = ProgressPDFGenerator(output_dir=tmp_path)
    path = gen.generate(progress_log, user_name="Con Historico", previous_logs=[prev2, prev1])

    reader = PdfReader(str(path))
    assert len(reader.pages) == 6
    # La página 2 debe contener una imagen embebida (el gráfico de peso).
    page2 = reader.pages[1]
    assert "/XObject" in page2["/Resources"]


def test_without_previous_logs_no_chart_but_valid(generated: Path) -> None:
    # Sin histórico no hay imagen; el informe sigue siendo válido y de 6 págs.
    reader = PdfReader(str(generated))
    page2 = reader.pages[1]
    resources = page2["/Resources"]
    assert "/XObject" not in resources
