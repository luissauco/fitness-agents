"""Tests de los repositorios SQLite."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest

from src.db.connection import init_schema
from src.db.repositories import (
    BodyAssessmentRepository,
    MesocycleRepository,
    NutritionPlanRepository,
    ProgressLogRepository,
    UserProfileRepository,
)
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

# --------------------------------------------------------------- Fixtures


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """SQLite efímera con esquema inicializado."""
    path: Path = tmp_path / "fitness.sqlite"
    init_schema(path)
    return path


@pytest.fixture
def sample_profile() -> UserProfile:
    return UserProfile(
        id="u1",
        created_at=datetime(2026, 5, 1, 10, 0, 0),
        updated_at=datetime(2026, 5, 1, 10, 0, 0),
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
        goals=Goals(primary_goal="recomposition", primary_goal_detail="—"),
        gym=GymEquipment(),
    )


def _macros(c: int = 2300, p: int = 160, ca: int = 265, f: int = 60) -> MacroDistribution:
    return MacroDistribution(calories=c, protein_g=p, carbs_g=ca, fat_g=f)


def _make_mesocycle(meso_id: str = "m1") -> Mesocycle:
    day = TrainingDay(
        day_number=1,
        day_label="Push",
        exercises=[
            ProgrammedExercise(
                order=1,
                exercise_id="bench",
                exercise_name="Press banca",
                set_scheme=SetScheme(total_sets=3, rep_range=(6, 10), rir=2, description="3x6-10"),
            )
        ],
    )
    micro = Microcycle(number=1, training_days=[day])
    return Mesocycle(
        id=meso_id,
        user_id="u1",
        name="Meso",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[micro],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="—",
    )


def _make_plan(plan_id: str = "p1") -> NutritionPlan:
    diet_train = DailyDiet(
        day_type="training",
        macros=_macros(),
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=150)])],
    )
    diet_rest = DailyDiet(
        day_type="rest",
        macros=_macros(c=2050, ca=200),
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=100)])],
    )
    return NutritionPlan(
        id=plan_id,
        user_id="u1",
        name="Plan",
        objective="—",
        phase="recomposition",
        duration="12 sem",
        start_date=date(2026, 5, 1),
        training_day_diet=diet_train,
        rest_day_diet=diet_rest,
        interchange_rules=InterchangeRules(vegetable_rule="x", fruit_rule="x"),
        general_tips=GeneralTips(sauce_rule="x", seasoning_notes="x"),
        neat_cardio_notes="—",
    )


def _make_assessment() -> BodyAssessment:
    return BodyAssessment(
        id="a1",
        user_id="u1",
        date=date(2026, 5, 1),
        measurements=BodyMeasurements(weight_kg=78.0),
        visual=VisualAssessment(
            estimated_body_fat_range=(15.0, 18.0),
            fat_distribution="abdominal",
            overall_impression="ok",
        ),
        metabolic=MetabolicEstimates.from_basic_data(
            weight_kg=78.0, height_cm=178.0, age=30, sex="M", activity_factor=1.55
        ),
        phase_recommendation=PhaseRecommendation(
            recommended_phase="recomposition",
            reasoning="ok",
            suggested_duration_weeks=8,
            suggested_calorie_target=2230,
            suggested_macros=_macros(2230, 150, 250, 70),
        ),
    )


def _make_log(log_id: str = "l1") -> ProgressLog:
    return ProgressLog(
        id=log_id,
        user_id="u1",
        mesocycle_id="m1",
        microcycle_number=1,
        date=date(2026, 5, 14),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 14),
        weight=WeightLog(weights=[78.0], average=78.0, trend="stable"),
        measurements=BodyMeasurements(weight_kg=78.0),
        training=TrainingProgress(
            exercises_tracked=1,
            exercises_progressed=1,
            exercises_stagnated=0,
            exercises_regressed=0,
            volume_adherence_pct=100.0,
        ),
        nutrition=NutritionAdherence(
            adherence_pct=85.0,
            cheat_meals_count=1,
            missed_meals_avg=0.0,
            supplement_adherence=True,
            water_intake_liters=2.5,
        ),
        subjective=SubjectiveFeedback(
            energy_level=7,
            sleep_quality=7,
            hunger_level=5,
            motivation=8,
            stress_level=4,
            soreness=4,
            mood=7,
        ),
        daily_steps_avg=10500,
        decision=ProgressDecision(action="continue", reasoning="—"),
        report_summary="—",
    )


# ----------------------------------------------------------------- Tests


def test_user_profile_save_and_get(db_path: Path, sample_profile: UserProfile) -> None:
    repo = UserProfileRepository(db_path)
    assert repo.get("u1") is None

    repo.save(sample_profile)
    loaded = repo.get("u1")
    assert loaded is not None
    assert loaded.personal.name == sample_profile.personal.name
    assert loaded.id == "u1"


def test_user_profile_upsert(db_path: Path, sample_profile: UserProfile) -> None:
    repo = UserProfileRepository(db_path)
    repo.save(sample_profile)
    sample_profile.personal.name = "Luis"
    repo.save(sample_profile)
    loaded = repo.get("u1")
    assert loaded is not None and loaded.personal.name == "Luis"


def test_mesocycle_history_ordered(db_path: Path) -> None:
    repo = MesocycleRepository(db_path)
    m1 = _make_mesocycle("meso-1")
    m1.created_at = datetime(2026, 4, 1)
    m2 = _make_mesocycle("meso-2")
    m2.created_at = datetime(2026, 5, 1)
    repo.save(m1)
    repo.save(m2)

    current = repo.get_current("u1")
    assert current is not None and current.id == "meso-2"

    history = repo.list_history("u1")
    assert [m.id for m in history] == ["meso-2", "meso-1"]


def test_nutrition_plan_get_current(db_path: Path) -> None:
    repo = NutritionPlanRepository(db_path)
    assert repo.get_current("u1") is None
    repo.save(_make_plan())
    current = repo.get_current("u1")
    assert current is not None and current.id == "p1"


def test_body_assessment_get_latest(db_path: Path) -> None:
    repo = BodyAssessmentRepository(db_path)
    a1 = _make_assessment()
    a2 = _make_assessment()
    a2.id = "a2"
    a2.date = date(2026, 6, 1)
    repo.save(a1)
    repo.save(a2)

    latest = repo.get_latest("u1")
    assert latest is not None and latest.id == "a2"


def test_progress_log_list_for_user(db_path: Path) -> None:
    repo = ProgressLogRepository(db_path)
    repo.save(_make_log("l1"))
    log2 = _make_log("l2")
    log2.date = date(2026, 5, 28)
    repo.save(log2)

    logs = repo.list_for_user("u1")
    assert [log.id for log in logs] == ["l2", "l1"]


def test_init_schema_idempotent(db_path: Path) -> None:
    """Llamar `init_schema` dos veces no debe romper."""
    init_schema(db_path)
    init_schema(db_path)
