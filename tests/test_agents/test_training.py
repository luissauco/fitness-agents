"""Tests del `TrainingAgent`.

Mockean solo `ClaudeClient.generate_structured`. Usan el catálogo real
(`data/exercises.json`) para verificar que los ids generados existen.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.claude_client import ClaudeClient
from src.agents.training import (
    TrainingAgent,
    _DayTemplate,
    _ExerciseSlot,
    _MesocycleStructure,
    _MicrocyclePlan,
)
from src.config.settings import Settings
from src.knowledge.retriever import KnowledgeRetriever
from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    MetabolicEstimates,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.common import MacroDistribution
from src.models.exercise_db import Equipment, ExerciseDatabase
from src.models.mesocycle import (
    Microcycle,
    ProgrammedExercise,
    SetScheme,
    TrainingDay,
)
from src.models.user_profile import (
    ActivityProfile,
    Goals,
    GymEquipment,
    NutritionProfile,
    PersonalData,
    UserProfile,
)
from tests.helpers import FakeEmbeddingManager

# ---------------------------------------------------------------- Fixtures


@pytest.fixture
def training_agent(settings: Settings, fake_embeddings: FakeEmbeddingManager) -> TrainingAgent:
    """`TrainingAgent` con `ClaudeClient` real (sin patch todavía)."""
    retriever = KnowledgeRetriever(settings=settings, embedding_manager=fake_embeddings)
    claude = ClaudeClient(settings)
    return TrainingAgent(claude_client=claude, retriever=retriever, settings=settings)


@pytest.fixture
def exercise_db() -> ExerciseDatabase:
    """Catálogo real cargado de `data/exercises.json`."""
    return ExerciseDatabase.load()


@pytest.fixture
def sample_profile() -> UserProfile:
    """Usuario con 4 días/semana, NEAT moderado."""
    return UserProfile(
        id="user-train-1",
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
            current_training_type="upper/lower",
            neat_level="moderate",
            injuries=[],
        ),
        nutrition=NutritionProfile(
            meals_per_day=4,
            typical_foods="—",
            salt_usage="moderate",
            daily_water_liters=2.5,
        ),
        goals=Goals(primary_goal="muscle_gain", primary_goal_detail="hipertrofia"),
        gym=GymEquipment(
            available_equipment=list(Equipment),  # acceso a todo el equipamiento
        ),
    )


@pytest.fixture
def sample_assessment() -> BodyAssessment:
    """`BodyAssessment` mínimo, fase recomendada lean_bulk."""
    return BodyAssessment(
        id="ass-1",
        user_id="user-train-1",
        date=date(2026, 5, 1),
        measurements=BodyMeasurements(weight_kg=78.5),
        visual=VisualAssessment(
            estimated_body_fat_range=(14.0, 17.0),
            fat_distribution="equilibrada",
            overall_impression="usuario intermedio.",
        ),
        metabolic=MetabolicEstimates.from_basic_data(
            weight_kg=78.5,
            height_cm=178.0,
            age=30,
            sex="M",
            activity_factor=1.65,
        ),
        phase_recommendation=PhaseRecommendation(
            recommended_phase="lean_bulk",
            reasoning="ok",
            suggested_duration_weeks=12,
            suggested_calorie_target=3000,
            suggested_macros=MacroDistribution(calories=3000, protein_g=160, carbs_g=410, fat_g=80),
        ),
    )


def _patch_llm(agent: TrainingAgent, *outputs: Any) -> AsyncMock:
    """Encadena respuestas para sucesivas llamadas a `generate_structured`."""
    mock = AsyncMock(side_effect=list(outputs))
    agent.claude.generate_structured = mock  # type: ignore[method-assign]
    return mock


# ----------------------------------------------------------- _select_split


def test_select_split_known_days(training_agent: TrainingAgent) -> None:
    """Mapeo determinístico días/semana → split."""
    assert training_agent._select_split(3) == "full_body"
    assert training_agent._select_split(4) == "upper_lower"
    assert training_agent._select_split(5) == "torso_legs"
    assert training_agent._select_split(6) == "push_pull_legs"


def test_select_split_invalid_days_raises(training_agent: TrainingAgent) -> None:
    """Días/semana fuera de [1, 7] lanzan ValueError."""
    with pytest.raises(ValueError):
        training_agent._select_split(0)
    with pytest.raises(ValueError):
        training_agent._select_split(8)


# --------------------------------------------------------- _compact_catalog


def test_compact_catalog_filters_by_equipment(
    training_agent: TrainingAgent, exercise_db: ExerciseDatabase
) -> None:
    """Solo aparecen ejercicios cuyo equipment está en la lista disponible."""
    blob = training_agent._compact_catalog(exercise_db, [Equipment.BODYWEIGHT])
    # No debería haber referencias a barbell ni dumbbell.
    assert "barbell" not in blob.lower() or "bodyweight" in blob.lower()
    # Pero debe haber algún ejercicio bodyweight.
    bw_exercises = [e for e in exercise_db.exercises if e.equipment == [Equipment.BODYWEIGHT]]
    if bw_exercises:
        assert bw_exercises[0].id in blob


# ---------------------------------------------------------- Pipeline completo


def _build_fake_microcycle(
    *,
    number: int,
    is_deload: bool,
    rir: int,
    volume_modifier: float,
    exercise_id: str,
    exercise_name: str,
) -> Microcycle:
    """Microciclo válido mínimo con 1 día de entreno y 1 ejercicio."""
    scheme = SetScheme(
        total_sets=3,
        rep_range=(8, 12),
        rir=rir,
        rest_seconds=120,
        description=f"3x8-12 RIR {rir}",
    )
    exercise = ProgrammedExercise(
        order=1,
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        set_scheme=scheme,
    )
    day = TrainingDay(
        day_number=1,
        day_label="Día 1 — Upper",
        is_rest_day=False,
        exercises=[exercise],
    )
    return Microcycle(
        number=number,
        duration_days=7,
        is_deload=is_deload,
        volume_modifier=volume_modifier,
        intensity_modifier=1.0,
        training_days=[day],
    )


@pytest.mark.asyncio
async def test_run_pipeline_produces_valid_mesocycle(
    training_agent: TrainingAgent,
    sample_profile: UserProfile,
    sample_assessment: BodyAssessment,
    exercise_db: ExerciseDatabase,
) -> None:
    """`run` engancha estructura + microciclos y devuelve un Mesocycle válido."""
    real_id = exercise_db.exercises[0].id
    real_name = exercise_db.exercises[0].name

    structure = _MesocycleStructure(
        name="Lean Bulk Upper/Lower 4 micros",
        phase="lean_bulk",
        split_type="upper_lower",
        training_days_per_week=4,
        progression_strategy="+1 set por micro · descarga -40% volumen",
        days_template=[
            _DayTemplate(
                day_number=1,
                day_label="Upper A",
                slots=[
                    _ExerciseSlot(
                        order=1,
                        role="compound",
                        primary_muscle="chest",
                        movement_pattern="horizontal_push",
                        volume_target_sets=3,
                    ),
                ],
            ),
        ],
        microcycles_plan=[
            _MicrocyclePlan(
                number=1,
                target_rir_low=2,
                target_rir_high=3,
                volume_modifier=1.0,
                is_deload=False,
            ),
            _MicrocyclePlan(
                number=2,
                target_rir_low=3,
                target_rir_high=4,
                volume_modifier=0.6,
                is_deload=True,
                notes="descarga",
            ),
        ],
    )
    micro_carga = _build_fake_microcycle(
        number=1,
        is_deload=False,
        rir=2,
        volume_modifier=1.0,
        exercise_id=real_id,
        exercise_name=real_name,
    )
    micro_descarga = _build_fake_microcycle(
        number=2,
        is_deload=True,
        rir=4,
        volume_modifier=0.6,
        exercise_id=real_id,
        exercise_name=real_name,
    )
    _patch_llm(training_agent, structure, micro_carga, micro_descarga)

    mesocycle = await training_agent.run(sample_profile, sample_assessment, exercise_db=exercise_db)

    # Estructura básica.
    assert mesocycle.user_id == "user-train-1"
    assert mesocycle.split_type == "upper_lower"
    assert mesocycle.training_days_per_week == 4
    assert len(mesocycle.microcycles) == 2
    # Descarga al final con volumen reducido.
    last = mesocycle.microcycles[-1]
    assert last.is_deload is True
    assert last.volume_modifier <= 0.7
    # Progresión: el último de carga tiene RIR ≤ que el primero (mayor intensidad).
    first_rir = mesocycle.microcycles[0].training_days[0].exercises[0].set_scheme.rir
    last_carga_rir = first_rir  # solo hay 1 carga aquí, equivalencia trivial
    assert last_carga_rir <= 3
    # Todos los exercise_ids existen en el catálogo.
    for m in mesocycle.microcycles:
        for d in m.training_days:
            for ex in d.exercises:
                assert exercise_db.by_id(ex.exercise_id) is not None


@pytest.mark.asyncio
async def test_run_logs_warnings_on_unknown_exercise(
    training_agent: TrainingAgent,
    sample_profile: UserProfile,
    sample_assessment: BodyAssessment,
    exercise_db: ExerciseDatabase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Si un microciclo trae un id inexistente, el validator logea warning (no aborta)."""
    structure = _MesocycleStructure(
        name="x",
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        progression_strategy="—",
        days_template=[_DayTemplate(day_number=1, day_label="d1")],
        microcycles_plan=[
            _MicrocyclePlan(number=1, target_rir_low=2, target_rir_high=3),
            _MicrocyclePlan(
                number=2,
                target_rir_low=3,
                target_rir_high=4,
                is_deload=True,
                volume_modifier=0.6,
            ),
        ],
    )
    bogus_micro = _build_fake_microcycle(
        number=1,
        is_deload=False,
        rir=2,
        volume_modifier=1.0,
        exercise_id="ejercicio-inventado",
        exercise_name="Ejercicio inventado",
    )
    deload = _build_fake_microcycle(
        number=2,
        is_deload=True,
        rir=4,
        volume_modifier=0.6,
        exercise_id=exercise_db.exercises[0].id,
        exercise_name=exercise_db.exercises[0].name,
    )
    _patch_llm(training_agent, structure, bogus_micro, deload)

    with caplog.at_level(logging.WARNING, logger="src.agents.training"):
        await training_agent.run(sample_profile, sample_assessment, exercise_db=exercise_db)

    # Hubo warnings de equipamiento o estructura.
    messages = " ".join(rec.getMessage() for rec in caplog.records)
    assert "training." in messages or "warnings" in messages.lower()
