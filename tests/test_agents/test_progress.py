"""Tests del `ProgressAgent`."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.claude_client import ClaudeClient
from src.agents.progress import ProgressAgent
from src.config.settings import Settings
from src.knowledge.retriever import KnowledgeRetriever
from src.models.body_assessment import BodyMeasurements
from src.models.checkin_input import CheckinInput
from src.models.common import MacroDistribution
from src.models.mesocycle import (
    Mesocycle,
    Microcycle,
    ProgrammedExercise,
    SetScheme,
    TrainingDay,
    WeeklySchedule,
)
from src.models.nutrition_plan import (
    DailyDiet,
    FoodItem,
    GeneralTips,
    InterchangeRules,
    Meal,
    NutritionPlan,
)
from src.models.progress_log import (
    NutritionAdherence,
    PhotoComparison,
    ProgressDecision,
    ProgressLog,
    SubjectiveFeedback,
    TrainingProgress,
    WeightLog,
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

# --------------------------------------------------------------- Fixtures


@pytest.fixture
def progress_agent(
    settings: Settings, fake_embeddings: FakeEmbeddingManager
) -> ProgressAgent:
    retriever = KnowledgeRetriever(settings=settings, embedding_manager=fake_embeddings)
    claude = ClaudeClient(settings)
    return ProgressAgent(claude_client=claude, retriever=retriever, settings=settings)


@pytest.fixture
def sample_profile() -> UserProfile:
    return UserProfile(
        id="user-prog-1",
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
        personal=PersonalData(
            name="L",
            age=30,
            sex="M",
            height_cm=178.0,
            weight_kg=78.0,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
        ),
        activity=ActivityProfile(
            training_days_per_week=4, rest_days_per_week=3, neat_level="moderate"
        ),
        nutrition=NutritionProfile(
            meals_per_day=4, typical_foods="—", salt_usage="moderate", daily_water_liters=2.5
        ),
        goals=Goals(primary_goal="fat_loss", primary_goal_detail="—"),
        gym=GymEquipment(),
        body_photo_paths=[],
    )


def _build_mesocycle(*, n_microcycles: int) -> Mesocycle:
    """Mesociclo con N microciclos; el último marcado como descarga."""
    micros: list[Microcycle] = []
    for i in range(n_microcycles):
        scheme = SetScheme(
            total_sets=3, rep_range=(8, 12), rir=2, rest_seconds=120, description="x"
        )
        ex = ProgrammedExercise(
            order=1, exercise_id="press-banca-barra-plano", exercise_name="Press", set_scheme=scheme
        )
        day = TrainingDay(day_number=1, day_label="d1", exercises=[ex])
        is_deload = i == n_microcycles - 1
        micros.append(
            Microcycle(
                number=i + 1,
                training_days=[day],
                is_deload=is_deload,
                volume_modifier=0.6 if is_deload else 1.0,
            )
        )
    return Mesocycle(
        id="meso-1",
        user_id="user-prog-1",
        name="meso",
        start_date=date(2026, 5, 1),
        phase="cut",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=micros,
        weekly_schedule=WeeklySchedule(),
        progression_strategy="—",
    )


def _build_nutrition_plan(phase: str = "cut") -> NutritionPlan:
    diet_train = DailyDiet(
        day_type="training",
        macros=MacroDistribution(calories=2300, protein_g=160, carbs_g=265, fat_g=60),
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=150)])],
    )
    diet_rest = DailyDiet(
        day_type="rest",
        macros=MacroDistribution(calories=2050, protein_g=160, carbs_g=200, fat_g=60),
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=100)])],
    )
    return NutritionPlan(
        id="plan-1",
        user_id="user-prog-1",
        name="plan",
        objective="—",
        phase=phase,  # type: ignore[arg-type]
        duration="12 semanas",
        start_date=date(2026, 5, 1),
        training_day_diet=diet_train,
        rest_day_diet=diet_rest,
        interchange_rules=InterchangeRules(
            vegetable_rule="x", fruit_rule="x"
        ),
        general_tips=GeneralTips(sauce_rule="x", seasoning_notes="x"),
        neat_cardio_notes="—",
    )


def _build_checkin(
    *,
    weights: list[float] | None = None,
    energy: int = 7,
    soreness: int = 4,
    pain: str | None = None,
    photos: list[str] | None = None,
) -> CheckinInput:
    return CheckinInput(
        weights=weights or [78.0, 77.8, 77.5, 77.3, 77.1, 76.9],
        measurements=BodyMeasurements(weight_kg=77.0),
        photos=photos,
        training_logs=[],
        nutrition_adherence_self_estimate=0.85,
        cheat_meals_count=1,
        daily_steps_avg=10500,
        subjective=SubjectiveFeedback(
            energy_level=energy,
            sleep_quality=7,
            hunger_level=5,
            motivation=8,
            stress_level=4,
            soreness=soreness,
            mood=7,
            pain_or_discomfort=pain,
        ),
    )


def _patch_llm(agent: ProgressAgent, *outputs: Any) -> AsyncMock:
    mock = AsyncMock(side_effect=list(outputs))
    agent.claude.generate_structured = mock  # type: ignore[method-assign]
    return mock


# ------------------------------------------------------------- Determinístico


def test_analyze_weight_trend_losing(progress_agent: ProgressAgent) -> None:
    """Bajada media frente al log anterior → trend = `losing`."""
    prev = ProgressLog(
        id="p0",
        user_id="user-prog-1",
        mesocycle_id="meso-1",
        microcycle_number=1,
        date=date(2026, 4, 17),
        period_start=date(2026, 4, 3),
        period_end=date(2026, 4, 17),
        weight=WeightLog(weights=[78.5, 78.4], average=78.45, trend="stable"),
        measurements=BodyMeasurements(weight_kg=78.4),
        training=TrainingProgress(
            exercises_tracked=0,
            exercises_progressed=0,
            exercises_stagnated=0,
            exercises_regressed=0,
            volume_adherence_pct=100.0,
        ),
        nutrition=NutritionAdherence(
            adherence_pct=85, cheat_meals_count=1, missed_meals_avg=0,
            supplement_adherence=True, water_intake_liters=2.5,
        ),
        subjective=SubjectiveFeedback(
            energy_level=7, sleep_quality=7, hunger_level=5,
            motivation=8, stress_level=4, soreness=4, mood=7,
        ),
        daily_steps_avg=10500,
        decision=ProgressDecision(action="continue", reasoning="—"),
        report_summary="—",
    )
    weight = progress_agent._analyze_weight_trend(
        weights=[77.5, 77.3, 77.1, 77.0], previous_logs=[prev]
    )
    assert weight.trend == "losing"
    assert weight.average < prev.weight.average


def test_forced_decision_new_mesocycle_at_end(progress_agent: ProgressAgent) -> None:
    """Si microcycle_completed == nº microciclos, fuerza `new_mesocycle`."""
    meso = _build_mesocycle(n_microcycles=4)
    forced = progress_agent._forced_decision(
        meso,
        microcycle_completed=4,
        subjective=SubjectiveFeedback(
            energy_level=7, sleep_quality=7, hunger_level=5,
            motivation=8, stress_level=4, soreness=4, mood=7,
        ),
        previous_logs=[],
    )
    assert forced == "new_mesocycle"


def test_forced_decision_early_deload_after_two_fatigued_periods(
    progress_agent: ProgressAgent,
) -> None:
    """Dos periodos seguidos con energía baja + DOMS alto → `early_deload`."""
    meso = _build_mesocycle(n_microcycles=5)
    fatigued_prev = ProgressLog(
        id="p_prev",
        user_id="user-prog-1",
        mesocycle_id="meso-1",
        microcycle_number=2,
        date=date(2026, 5, 1),
        period_start=date(2026, 4, 17),
        period_end=date(2026, 5, 1),
        weight=WeightLog(weights=[78.0], average=78.0, trend="stable"),
        measurements=BodyMeasurements(weight_kg=78.0),
        training=TrainingProgress(
            exercises_tracked=0, exercises_progressed=0, exercises_stagnated=0,
            exercises_regressed=0, volume_adherence_pct=100.0,
        ),
        nutrition=NutritionAdherence(
            adherence_pct=85, cheat_meals_count=1, missed_meals_avg=0,
            supplement_adherence=True, water_intake_liters=2.5,
        ),
        subjective=SubjectiveFeedback(
            energy_level=3, sleep_quality=4, hunger_level=6, motivation=4,
            stress_level=7, soreness=8, mood=4,
        ),
        daily_steps_avg=9000,
        decision=ProgressDecision(action="continue", reasoning="—"),
        report_summary="—",
    )
    forced = progress_agent._forced_decision(
        meso,
        microcycle_completed=3,
        subjective=SubjectiveFeedback(
            energy_level=3, sleep_quality=5, hunger_level=6, motivation=5,
            stress_level=6, soreness=8, mood=5,
        ),
        previous_logs=[fatigued_prev],
    )
    assert forced == "early_deload"


# --------------------------------------------------------------- Pipeline run()


@pytest.mark.asyncio
async def test_run_returns_valid_progress_log_without_photos(
    progress_agent: ProgressAgent,
    sample_profile: UserProfile,
) -> None:
    """`run` sin fotos hace una sola llamada al LLM (decisión)."""
    meso = _build_mesocycle(n_microcycles=4)
    plan = _build_nutrition_plan(phase="cut")
    checkin = _build_checkin()
    decision = ProgressDecision(
        action="adjust_calories",
        reasoning="Pérdida lenta de peso, recortamos 200 kcal.",
        details={"calorie_change": -200},
    )
    mock = _patch_llm(progress_agent, decision)

    log = await progress_agent.run(
        sample_profile, meso, plan, checkin, previous_logs=[]
    )

    assert log.user_id == "user-prog-1"
    assert log.mesocycle_id == meso.id
    assert log.decision.action == "adjust_calories"
    assert log.photos is None
    # Periodo correcto.
    assert log.period_end - log.period_start == timedelta(days=14)
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_run_with_photos_calls_llm_twice(
    progress_agent: ProgressAgent,
    sample_profile: UserProfile,
    tmp_path,
) -> None:
    """Si hay fotos, el agente llama 2 veces al LLM (vision + decisión)."""
    meso = _build_mesocycle(n_microcycles=4)
    plan = _build_nutrition_plan(phase="cut")
    img_path = tmp_path / "frente.jpg"
    img_path.write_bytes(b"\xff\xd8fakejpg")
    checkin = _build_checkin(photos=[str(img_path)])
    sample_profile.body_photo_paths = [str(img_path)]

    photos = PhotoComparison(
        current_photos=[str(img_path)],
        visual_changes="cintura más definida",
        areas_improved=["cintura"],
        areas_unchanged=["piernas"],
    )
    decision = ProgressDecision(action="continue", reasoning="ok")
    mock = _patch_llm(progress_agent, photos, decision)

    log = await progress_agent.run(
        sample_profile, meso, plan, checkin, previous_logs=[]
    )

    assert log.photos is not None
    assert "cintura" in log.photos.visual_changes
    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_run_at_last_microcycle_passes_forced_decision_in_prompt(
    progress_agent: ProgressAgent,
    sample_profile: UserProfile,
) -> None:
    """En el último microciclo, el prompt insta a usar `new_mesocycle`."""
    meso = _build_mesocycle(n_microcycles=2)
    plan = _build_nutrition_plan(phase="cut")
    checkin = _build_checkin()
    decision = ProgressDecision(action="new_mesocycle", reasoning="—")
    mock = _patch_llm(progress_agent, decision)

    await progress_agent.run(
        sample_profile, meso, plan, checkin, previous_logs=[], microcycle_completed=2
    )

    sent_prompt = mock.await_args.kwargs["user_message"]
    assert "new_mesocycle" in sent_prompt
