"""Tests del generador PDF nutricional."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from src.generators.pdf_nutrition import NutritionPDFGenerator
from src.models.nutrition_plan import NutritionPlan


def _text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() for page in reader.pages)


@pytest.fixture
def generated(tmp_path: Path, nutrition_plan: NutritionPlan) -> Path:
    gen = NutritionPDFGenerator(output_dir=tmp_path)
    return gen.generate(nutrition_plan, user_name="Luis Sauco")


def test_file_created(generated: Path) -> None:
    assert generated.exists()
    assert generated.suffix == ".pdf"
    assert "Luis_Sauco" in generated.name


def test_page_count(generated: Path) -> None:
    reader = PdfReader(str(generated))
    # Portada + entreno + descanso + comparativa + cheat + tips + neat = 7.
    assert len(reader.pages) >= 7


def test_key_content_present(generated: Path) -> None:
    text = _text(generated)
    assert "PROGRAMA NUTRICIONAL" in text
    assert "Luis Sauco" in text
    assert "DÍAS DE ENTRENO" in text
    assert "DÍAS DE DESCANSO" in text
    assert "2100 KCAL" in text
    assert "Avena" in text
    assert "PROTOCOLO DE COMIDA LIBRE" in text
    assert "CARDIO Y NEAT" in text


def test_cheat_protocol_omitted_when_none(tmp_path: Path, nutrition_plan: NutritionPlan) -> None:
    nutrition_plan.cheat_meal_protocol = None
    gen = NutritionPDFGenerator(output_dir=tmp_path)
    path = gen.generate(nutrition_plan, user_name="Sin Cheat")
    reader = PdfReader(str(path))
    assert len(reader.pages) >= 6
    assert "PROTOCOLO DE COMIDA LIBRE" not in _text(path)
