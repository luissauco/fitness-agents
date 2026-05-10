"""Tests del `NutritionAgent`."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.claude_client import ClaudeClient
from src.agents.nutrition import NutritionAgent
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
from src.models.mesocycle import (
    Mesocycle,
    Microcycle,
    ProgrammedExercise,
    SetScheme,
    TrainingDay,
    WeeklySchedule,
)
from src.models.nutrition_plan import DailyDiet, FoodItem, Meal
from src.models.user_profile import (
    ActivityProfile,
    Goals,
    GymEquipment,
    NutritionProfile,
    PersonalData,
    UserProfile,
)
from src.models.validators import validate_macros_consistency
from tests.helpers import FakeEmbeddingManager

# ---------------------------------------------------------------- Fixtures


@pytest.fixture
def nutrition_agent(settings: Settings, fake_embeddings: FakeEmbeddingManager) -> NutritionAgent:
    """`NutritionAgent` con `ClaudeClient` real (sin patch todavía)."""
    retriever = KnowledgeRetriever(settings=settings, embedding_manager=fake_embeddings)
    claude = ClaudeClient(settings)
    return NutritionAgent(claude_client=claude, retriever=retriever, settings=settings)


@pytest.fixture
def sample_profile() -> UserProfile:
    """Perfil con alergia a lácteos para verificar que se propaga."""
    return UserProfile(
        id="user-nut-1",
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
        personal=PersonalData(
            name="Luis",
            age=30,
            sex="M",
            height_cm=178.0,
            weight_kg=78.0,
            wake_time=time(7, 0),
            sleep_time=time(23, 30),
        ),
        activity=ActivityProfile(
            training_days_per_week=4,
            rest_days_per_week=3,
            neat_level="moderate",
            training_time=time(18, 0),
        ),
        nutrition=NutritionProfile(
            meals_per_day=4,
            typical_foods="arroz, pollo",
            salt_usage="moderate",
            daily_water_liters=2.5,
            allergies=["lácteos"],
            disliked_foods=["coliflor"],
            comfortable_food_groups=["arroz / pasta", "carnes"],
            open_to_supplements=True,
        ),
        goals=Goals(primary_goal="muscle_gain", primary_goal_detail="ganar 3 kg"),
        gym=GymEquipment(),
    )


def _make_assessment(phase: str, tdee: float = 2700) -> BodyAssessment:
    """`BodyAssessment` mínimo con la fase indicada."""
    return BodyAssessment(
        id="ass-1",
        user_id="user-nut-1",
        date=date(2026, 5, 1),
        measurements=BodyMeasurements(weight_kg=78.0),
        visual=VisualAssessment(
            estimated_body_fat_range=(14.0, 17.0),
            fat_distribution="—",
            overall_impression="—",
        ),
        metabolic=MetabolicEstimates(
            bmr=1700.0,
            tdee=tdee,
            activity_factor=1.6,
            bmi=24.5,
        ),
        phase_recommendation=PhaseRecommendation(
            recommended_phase=phase,
            reasoning="—",
            suggested_duration_weeks=12,
            suggested_calorie_target=int(tdee),
            suggested_macros=MacroDistribution(calories=2700, protein_g=156, carbs_g=320, fat_g=70),
        ),
    )


@pytest.fixture
def assessment_lean_bulk() -> BodyAssessment:
    return _make_assessment("lean_bulk")


@pytest.fixture
def sample_mesocycle() -> Mesocycle:
    """Mesociclo mínimo válido."""
    scheme = SetScheme(total_sets=3, rep_range=(8, 12), rir=2, rest_seconds=120, description="x")
    ex = ProgrammedExercise(order=1, exercise_id="x", exercise_name="X", set_scheme=scheme)
    day = TrainingDay(day_number=1, day_label="d1", is_rest_day=False, exercises=[ex])
    micro = Microcycle(number=1, training_days=[day])
    return Mesocycle(
        id="meso-1",
        user_id="user-nut-1",
        name="meso",
        start_date=date(2026, 5, 1),
        phase="lean_bulk",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[micro],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="—",
    )


def _patch_llm(agent: NutritionAgent, *outputs: Any) -> AsyncMock:
    mock = AsyncMock(side_effect=list(outputs))
    agent.claude.generate_structured = mock  # type: ignore[method-assign]
    return mock


def _make_diet(day_type: str, *, calories: int, carbs_g: int) -> DailyDiet:
    """`DailyDiet` mínima válida con macros consistentes."""
    protein_g = 156
    fat_g = 70
    actual_kcal = protein_g * 4 + carbs_g * 4 + fat_g * 9
    return DailyDiet(
        day_type=day_type,  # type: ignore[arg-type]
        macros=MacroDistribution(
            calories=actual_kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g
        ),
        meals=[
            Meal(
                name="Comida 1",
                foods=[
                    FoodItem(
                        name="arroz cocido",
                        amount_g=150,
                        alternatives=["pasta cocida", "patata cocida"],
                        alternative_amounts=["150g de pasta cocida", "675g de patata"],
                    )
                ],
            )
        ],
    )


# ----------------------------------------------------- _calculate_target_macros


def test_calculate_target_macros_cut_under_tdee(
    nutrition_agent: NutritionAgent, sample_profile: UserProfile
) -> None:
    """En cut, las calorías de entreno bajan respecto al TDEE."""
    assessment = _make_assessment("cut", tdee=2800)
    macros = nutrition_agent._calculate_target_macros(
        sample_profile, assessment, day_type="training"
    )
    assert macros.calories < assessment.metabolic.tdee
    # Y siempre por encima del BMR.
    assert macros.calories >= assessment.metabolic.bmr


def test_target_macros_in_lean_bulk_above_tdee(
    nutrition_agent: NutritionAgent,
    sample_profile: UserProfile,
    assessment_lean_bulk: BodyAssessment,
) -> None:
    """En lean_bulk, las calorías de entreno superan el TDEE."""
    macros = nutrition_agent._calculate_target_macros(
        sample_profile, assessment_lean_bulk, day_type="training"
    )
    assert macros.calories > assessment_lean_bulk.metabolic.tdee


def test_training_day_has_more_carbs_than_rest_day(
    nutrition_agent: NutritionAgent,
    sample_profile: UserProfile,
    assessment_lean_bulk: BodyAssessment,
) -> None:
    """En descanso bajan los HC, no la proteína ni la grasa."""
    train = nutrition_agent._calculate_target_macros(
        sample_profile, assessment_lean_bulk, day_type="training"
    )
    rest = nutrition_agent._calculate_target_macros(
        sample_profile, assessment_lean_bulk, day_type="rest"
    )
    assert rest.carbs_g < train.carbs_g
    assert rest.protein_g == train.protein_g
    assert rest.fat_g == train.fat_g
    assert rest.calories < train.calories


def test_target_macros_consistency_within_tolerance(
    nutrition_agent: NutritionAgent,
    sample_profile: UserProfile,
    assessment_lean_bulk: BodyAssessment,
) -> None:
    """`validate_macros_consistency` acepta los macros generados."""
    for day_type in ("training", "rest"):
        macros = nutrition_agent._calculate_target_macros(
            sample_profile,
            assessment_lean_bulk,
            day_type=day_type,  # type: ignore[arg-type]
        )
        assert validate_macros_consistency(macros)


# -------------------------------------------------------- Reglas de intercambio


def test_interchange_rules_canonical(nutrition_agent: NutritionAgent) -> None:
    """Las reglas de intercambio son las mismas siempre y cumplen el contrato."""
    rules = nutrition_agent._build_interchange_rules()
    assert "patata" in rules.carb_sources["100g arroz cocido"].lower()
    assert "pollo" in rules.protein_sources
    assert "plátano" in rules.fruit_rule.lower()
    assert rules.vegetable_rule


# -------------------------------------------------------------- Pipeline run()


@pytest.mark.asyncio
async def test_run_passes_allergies_to_llm(
    nutrition_agent: NutritionAgent,
    sample_profile: UserProfile,
    assessment_lean_bulk: BodyAssessment,
    sample_mesocycle: Mesocycle,
) -> None:
    """El user message del LLM incluye la lista de alergias del usuario."""
    train_diet = _make_diet("training", calories=3050, carbs_g=410)
    rest_diet = _make_diet("rest", calories=2750, carbs_g=335)
    mock = _patch_llm(nutrition_agent, train_diet, rest_diet)

    plan = await nutrition_agent.run(sample_profile, assessment_lean_bulk, sample_mesocycle)

    assert plan.training_day_diet.day_type == "training"
    assert plan.rest_day_diet.day_type == "rest"
    assert plan.phase == "lean_bulk"
    # Cada llamada al LLM debió llevar las alergias en el prompt.
    for call in mock.await_args_list:
        prompt = call.kwargs["user_message"]
        assert "lácteos" in prompt
        assert "ALERGIAS" in prompt


@pytest.mark.asyncio
async def test_run_assembles_plan_with_constants(
    nutrition_agent: NutritionAgent,
    sample_profile: UserProfile,
    assessment_lean_bulk: BodyAssessment,
    sample_mesocycle: Mesocycle,
) -> None:
    """`run` produce un `NutritionPlan` con reglas, tips y cheat protocol."""
    train_diet = _make_diet("training", calories=3050, carbs_g=410)
    rest_diet = _make_diet("rest", calories=2750, carbs_g=335)
    _patch_llm(nutrition_agent, train_diet, rest_diet)

    plan = await nutrition_agent.run(sample_profile, assessment_lean_bulk, sample_mesocycle)

    assert plan.user_id == "user-nut-1"
    assert plan.cheat_meal_protocol is not None
    assert plan.general_tips.tips
    assert plan.interchange_rules.protein_sources
    assert plan.calorie_difference > 0


# ------------------------------------------------------------ _enforce_minimums


def test_enforce_minimums_rejects_low_protein(nutrition_agent: NutritionAgent) -> None:
    """Si la proteína cae por debajo de 1.6 g/kg, se levanta ValueError."""
    profile_skel = UserProfile(
        id="x",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        personal=PersonalData(
            name="x",
            age=30,
            sex="M",
            height_cm=178.0,
            weight_kg=80.0,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
        ),
        activity=ActivityProfile(
            training_days_per_week=4,
            rest_days_per_week=3,
            neat_level="moderate",
        ),
        nutrition=NutritionProfile(
            meals_per_day=4,
            typical_foods="—",
            salt_usage="moderate",
            daily_water_liters=2.0,
        ),
        goals=Goals(primary_goal="muscle_gain", primary_goal_detail="—"),
        gym=GymEquipment(),
    )
    bad_macros = MacroDistribution(
        calories=80 * 4 + 400 * 4 + 70 * 9,  # 320+1600+630 = 2550
        protein_g=80,  # 1.0 g/kg — por debajo de 1.6
        carbs_g=400,
        fat_g=70,
    )
    with pytest.raises(ValueError, match="Proteína"):
        nutrition_agent._enforce_minimums(profile_skel, bad_macros)
