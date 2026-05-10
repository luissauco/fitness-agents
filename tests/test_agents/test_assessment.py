"""Tests del `AssessmentAgent`.

Mockean solo `ClaudeClient.generate_structured`. El RAG es real (vector store
vacío en `tmp_path`) — devuelve cadena vacía y el agente sigue funcionando.
"""

from __future__ import annotations

from datetime import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.assessment import _ACTIVITY_FACTORS, AssessmentAgent, _navy_body_fat
from src.agents.claude_client import ClaudeClient
from src.config.settings import Settings
from src.knowledge.retriever import KnowledgeRetriever
from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.common import MacroDistribution
from src.models.user_profile import (
    ActivityProfile,
    Goals,
    GymEquipment,
    NutritionProfile,
    PersonalData,
    UserProfile,
)
from tests.helpers import FakeEmbeddingManager

# ----------------------------------------------------------------- Fixtures


@pytest.fixture
def assessment_agent(settings: Settings, fake_embeddings: FakeEmbeddingManager) -> AssessmentAgent:
    """`AssessmentAgent` con `ClaudeClient` real (sin patch todavía)."""
    retriever = KnowledgeRetriever(settings=settings, embedding_manager=fake_embeddings)
    claude = ClaudeClient(settings)
    return AssessmentAgent(claude_client=claude, retriever=retriever, settings=settings)


@pytest.fixture
def sample_profile() -> UserProfile:
    """Usuario tipo: hombre, 30, 78 kg, 178 cm, NEAT moderado, 4 entrenos/sem."""
    from datetime import datetime

    return UserProfile(
        id="user-1",
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
        personal=PersonalData(
            name="Luis",
            age=30,
            sex="M",
            height_cm=178.0,
            weight_kg=78.5,
            wake_time=time(7, 0),
            sleep_time=time(23, 30),
        ),
        activity=ActivityProfile(
            training_days_per_week=4,
            rest_days_per_week=3,
            current_training_type="PPL",
            training_time=time(18, 0),
            neat_level="moderate",
            injuries=[],
        ),
        nutrition=NutritionProfile(
            meals_per_day=4,
            typical_foods="arroz, pollo, huevos",
            salt_usage="moderate",
            daily_water_liters=2.5,
        ),
        goals=Goals(
            primary_goal="muscle_gain",
            primary_goal_detail="3 kg en 4 meses",
        ),
        gym=GymEquipment(),
        body_photo_paths=[],
    )


@pytest.fixture
def sample_measurements() -> BodyMeasurements:
    """Medidas con cintura/cadera/cuello para activar la fórmula Navy."""
    return BodyMeasurements(
        weight_kg=78.5,
        waist_cm=82.0,
        hip_cm=98.0,
        neck_cm=38.0,
    )


def _patch_llm(agent: AssessmentAgent, *outputs: Any) -> AsyncMock:
    """Encadena respuestas para sucesivas llamadas a `generate_structured`."""
    mock = AsyncMock(side_effect=list(outputs))
    agent.claude.generate_structured = mock  # type: ignore[method-assign]
    return mock


# ------------------------------------------------------------- Cálculos puros


def test_activity_factor_mapping_covers_all_buckets() -> None:
    """Todos los pares (NEAT, bucket) están definidos en el mapping."""
    for neat in ("low", "moderate", "high"):
        for bucket in ("low", "mid", "high"):
            assert (neat, bucket) in _ACTIVITY_FACTORS
            assert 1.2 <= _ACTIVITY_FACTORS[(neat, bucket)] <= 1.9


def test_calculate_metabolic_estimates_known_values(
    assessment_agent: AssessmentAgent,
    sample_profile: UserProfile,
    sample_measurements: BodyMeasurements,
) -> None:
    """BMR Mifflin-St Jeor con M, 30y, 178cm, 78.5kg → 1736.25 kcal."""
    metabolic = assessment_agent._calculate_metabolic_estimates(sample_profile, sample_measurements)
    # 10*78.5 + 6.25*178 - 5*30 + 5 = 1752.5 (redondeado a 1 decimal por modelo)
    assert metabolic.bmr == pytest.approx(1752.5, abs=0.5)
    # NEAT moderate + 4 train (mid bucket) → 1.65
    assert metabolic.activity_factor == pytest.approx(1.65)
    assert metabolic.tdee == pytest.approx(metabolic.bmr * 1.65, abs=1.0)
    # IMC = 78.5 / 1.78² ≈ 24.78
    assert metabolic.bmi == pytest.approx(24.78, abs=0.05)
    # WHR = 82 / 98 ≈ 0.837
    assert metabolic.waist_hip_ratio == pytest.approx(0.837, abs=0.005)
    # Fórmula Navy aplicable.
    assert metabolic.estimated_bf_formula is not None
    assert 5 < metabolic.estimated_bf_formula < 30


def test_navy_body_fat_male_with_full_measurements() -> None:
    """Para un hombre con waist=82, neck=38, height=178: ~13-17 %."""
    bf = _navy_body_fat(sex="M", height_cm=178.0, waist_cm=82.0, neck_cm=38.0, hip_cm=None)
    assert bf is not None
    assert 10 <= bf <= 22


def test_navy_body_fat_returns_none_when_missing_measurements() -> None:
    """Sin cintura o sin cuello no se puede calcular."""
    no_waist = _navy_body_fat(sex="M", height_cm=178.0, waist_cm=None, neck_cm=38.0, hip_cm=None)
    no_neck = _navy_body_fat(sex="M", height_cm=178.0, waist_cm=82.0, neck_cm=None, hip_cm=None)
    assert no_waist is None
    assert no_neck is None


def test_navy_body_fat_female_requires_hip() -> None:
    """En mujeres la fórmula necesita cadera; sin ella retorna None."""
    assert (
        _navy_body_fat(sex="F", height_cm=165.0, waist_cm=70.0, neck_cm=32.0, hip_cm=None) is None
    )
    bf = _navy_body_fat(sex="F", height_cm=165.0, waist_cm=70.0, neck_cm=32.0, hip_cm=95.0)
    assert bf is not None
    assert 15 <= bf <= 35


# ------------------------------------------------------------------------- Run


@pytest.mark.asyncio
async def test_run_pipeline_produces_valid_body_assessment(
    assessment_agent: AssessmentAgent,
    sample_profile: UserProfile,
    sample_measurements: BodyMeasurements,
) -> None:
    """`run` enlaza vision + recomendación y devuelve un `BodyAssessment` válido."""
    visual = VisualAssessment(
        estimated_body_fat_range=(14.0, 17.0),
        fat_distribution="distribución equilibrada con leve acumulación abdominal",
        muscle_development={"chest": "developed", "back": "average"},
        weak_points=["back", "rear_delts"],
        strong_points=["chest", "quads"],
        overall_impression="Compleción intermedia con masa muscular relevante.",
    )
    recommendation = PhaseRecommendation(
        recommended_phase="lean_bulk",
        reasoning="% graso 14-17% y objetivo muscle_gain encajan con superávit moderado.",
        suggested_duration_weeks=12,
        suggested_calorie_target=3000,
        suggested_macros=MacroDistribution(calories=3000, protein_g=160, carbs_g=410, fat_g=80),
    )
    _patch_llm(assessment_agent, visual, recommendation)

    result: BodyAssessment = await assessment_agent.run(sample_profile, sample_measurements)

    assert result.user_id == "user-1"
    assert result.visual.estimated_body_fat_range == (14.0, 17.0)
    assert result.phase_recommendation.recommended_phase == "lean_bulk"
    # kcal coherentes con la fase: lean_bulk → > TDEE.
    assert result.phase_recommendation.suggested_calorie_target > result.metabolic.tdee
    # Macros consistentes con kcal totales (validado por el agente).
    macros = result.phase_recommendation.suggested_macros
    assert abs(macros.protein_kcal + macros.carbs_kcal + macros.fat_kcal - macros.calories) <= 50


@pytest.mark.asyncio
async def test_run_handles_missing_photos_without_failing(
    assessment_agent: AssessmentAgent,
    sample_profile: UserProfile,
    sample_measurements: BodyMeasurements,
) -> None:
    """Si las fotos no existen, el agente sigue (vision call sin imágenes)."""
    sample_profile.body_photo_paths = ["/no/existe.jpg"]
    visual = VisualAssessment(
        estimated_body_fat_range=(15.0, 18.0),
        fat_distribution="—",
        overall_impression="Análisis sin fotos disponibles.",
    )
    recommendation = PhaseRecommendation(
        recommended_phase="recomposition",
        reasoning="Sin fotos, recomendación conservadora.",
        suggested_duration_weeks=8,
        suggested_calorie_target=2900,
        suggested_macros=MacroDistribution(calories=2900, protein_g=160, carbs_g=410, fat_g=70),
    )
    _patch_llm(assessment_agent, visual, recommendation)

    result = await assessment_agent.run(sample_profile, sample_measurements)
    assert result is not None
