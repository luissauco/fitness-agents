"""Tests del orquestador LangGraph (`src/graph/workflow.py`).

Mockeamos los agentes (devuelven outputs canónicos) y verificamos:
- Routing condicional según fase y datos del estado.
- Transiciones de estado al ejecutar el grafo end-to-end con mocks.
- Reanudación: `pending_checkin_data` en estado `checkin` dispara `progress`.
"""

from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.state import initial_state
from src.graph.workflow import (
    AgentBundle,
    build_workflow,
    route_after_planning,
    route_after_progress,
    route_entry,
)
from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    MetabolicEstimates,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.checkin_input import CheckinInput
from src.models.common import MacroDistribution
from src.models.intake_session import IntakeSession, IntakeTurn
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
from src.models.questionnaire import Questionnaire
from src.models.user_profile import (
    ActivityProfile,
    Goals,
    GymEquipment,
    NutritionProfile,
    PersonalData,
    UserProfile,
)

# --------------------------------------------------------------- Factories


def _make_profile(user_id: str = "u1") -> UserProfile:
    return UserProfile(
        id=user_id,
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
        personal=PersonalData(
            name="Luis",
            age=30,
            sex="M",
            height_cm=178.0,
            weight_kg=78.0,
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
            typical_foods="arroz, pollo, verduras",
            salt_usage="moderate",
            daily_water_liters=2.5,
        ),
        goals=Goals(
            primary_goal="recomposition", primary_goal_detail="bajar 3 kg manteniendo fuerza"
        ),
        gym=GymEquipment(),
    )


def _make_assessment(profile: UserProfile) -> BodyAssessment:
    macros = MacroDistribution(protein_g=150, fat_g=70, carbs_g=250, calories=2230)
    return BodyAssessment(
        id="a1",
        user_id=profile.id,
        date=date(2026, 5, 1),
        measurements=BodyMeasurements(weight_kg=profile.personal.weight_kg),
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
            suggested_macros=macros,
        ),
    )


def _make_mesocycle(num_micros: int = 4, mesocycle_id: str = "m1") -> Mesocycle:
    micros: list[Microcycle] = []
    for i in range(num_micros):
        is_deload = i == num_micros - 1
        day = TrainingDay(
            day_number=1,
            day_label="Día 1 - Push",
            exercises=[
                ProgrammedExercise(
                    order=1,
                    exercise_id="bench_press",
                    exercise_name="Press banca",
                    set_scheme=SetScheme(
                        total_sets=3, rep_range=(6, 10), rir=2, description="3x6-10 RIR2"
                    ),
                )
            ],
        )
        micros.append(
            Microcycle(
                number=i + 1,
                training_days=[day],
                is_deload=is_deload,
                volume_modifier=0.6 if is_deload else 1.0,
            )
        )
    return Mesocycle(
        id=mesocycle_id,
        user_id="u1",
        name="Hipertrofia",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=micros,
        weekly_schedule=WeeklySchedule(),
        progression_strategy="+1 RIR/-1 set deload",
    )


def _make_nutrition_plan() -> NutritionPlan:
    macros_train = MacroDistribution(calories=2300, protein_g=160, carbs_g=265, fat_g=60)
    macros_rest = MacroDistribution(calories=2050, protein_g=160, carbs_g=200, fat_g=60)
    diet_train = DailyDiet(
        day_type="training",
        macros=macros_train,
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=150)])],
    )
    diet_rest = DailyDiet(
        day_type="rest",
        macros=macros_rest,
        meals=[Meal(name="C1", foods=[FoodItem(name="arroz", amount_g=100)])],
    )
    return NutritionPlan(
        id="np1",
        user_id="u1",
        name="Plan",
        objective="recomposición",
        phase="recomposition",
        duration="12 semanas",
        start_date=date(2026, 5, 1),
        training_day_diet=diet_train,
        rest_day_diet=diet_rest,
        interchange_rules=InterchangeRules(vegetable_rule="x", fruit_rule="x"),
        general_tips=GeneralTips(sauce_rule="x", seasoning_notes="x"),
        neat_cardio_notes="—",
    )


def _make_progress_log(action: str = "continue") -> ProgressLog:
    return ProgressLog(
        id="p1",
        user_id="u1",
        mesocycle_id="m1",
        microcycle_number=1,
        date=date.today(),
        period_start=date(2026, 4, 26),
        period_end=date.today(),
        weight=WeightLog(weights=[78.0], average=78.0, trend="stable", change_from_last=0.0),
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
            soreness=5,
            mood=7,
        ),
        daily_steps_avg=10500,
        decision=ProgressDecision(action=action, reasoning="ok"),
        report_summary="Periodo estable.",
    )


def _make_checkin() -> CheckinInput:
    return CheckinInput(
        weights=[78.0, 77.9, 78.1],
        measurements=BodyMeasurements(weight_kg=78.0),
        nutrition_adherence_self_estimate=0.85,
        cheat_meals_count=1,
        daily_steps_avg=10500,
        subjective=SubjectiveFeedback(
            energy_level=7,
            sleep_quality=7,
            hunger_level=5,
            motivation=8,
            stress_level=4,
            soreness=5,
            mood=7,
        ),
    )


# ---------------------------------------------------------------- Bundles


def _make_bundle(
    *,
    intake_turn: IntakeTurn | None = None,
    profile: UserProfile | None = None,
    assessment: BodyAssessment | None = None,
    mesocycle: Mesocycle | None = None,
    nutrition_plan: NutritionPlan | None = None,
    progress_log: ProgressLog | None = None,
) -> AgentBundle:
    """Construye un `AgentBundle` con MagicMocks que devuelven outputs canónicos."""
    intake = MagicMock()
    intake.start_session = AsyncMock(
        return_value=IntakeSession(
            id="s1",
            user_id="u1",
            started_at=datetime(2026, 5, 1),
            questionnaire=Questionnaire.get_default(),
            current_block="personales",
        )
    )
    intake.process_response = AsyncMock(
        return_value=intake_turn or IntakeTurn(assistant_message="¿Edad?", is_complete=False)
    )
    intake.build_profile = AsyncMock(return_value=profile or _make_profile())

    assessment_agent = MagicMock()
    assessment_agent.run = AsyncMock(return_value=assessment or _make_assessment(_make_profile()))

    training = MagicMock()
    training.run = AsyncMock(return_value=mesocycle or _make_mesocycle())

    nutrition = MagicMock()
    nutrition.run = AsyncMock(return_value=nutrition_plan or _make_nutrition_plan())

    progress = MagicMock()
    progress.run = AsyncMock(return_value=progress_log or _make_progress_log())

    return AgentBundle(
        intake=intake,
        assessment=assessment_agent,
        training=training,
        nutrition=nutrition,
        progress=progress,
    )


# --------------------------------------------------------------- Tests routers


def test_route_entry_onboarding() -> None:
    state = initial_state("u1")
    assert route_entry(state) == "intake"


def test_route_entry_assessment() -> None:
    state = initial_state("u1")
    state["current_phase"] = "assessment"
    assert route_entry(state) == "assessment"


def test_route_entry_planning() -> None:
    state = initial_state("u1")
    state["current_phase"] = "planning"
    assert route_entry(state) == "training"


def test_route_entry_checkin_requires_data() -> None:
    state = initial_state("u1")
    state["current_phase"] = "checkin"
    # Sin pending_checkin_data, no entra al nodo progress.
    from langgraph.graph import END

    assert route_entry(state) == END
    state["pending_checkin_data"] = _make_checkin()
    assert route_entry(state) == "progress"


def test_route_after_progress_dispatches_by_action() -> None:
    state = initial_state("u1")
    state["progress_logs"] = [_make_progress_log(action="continue")]
    assert route_after_progress(state) == "advance_microcycle"

    state["progress_logs"] = [_make_progress_log(action="adjust_calories")]
    assert route_after_progress(state) == "nutrition"

    state["progress_logs"] = [_make_progress_log(action="adjust_volume")]
    assert route_after_progress(state) == "training"

    state["progress_logs"] = [_make_progress_log(action="new_mesocycle")]
    assert route_after_progress(state) == "training"


def test_route_after_planning_needs_both_outputs() -> None:
    state = initial_state("u1")
    state["current_mesocycle"] = _make_mesocycle()
    state["current_nutrition_plan"] = _make_nutrition_plan()
    assert route_after_planning(state) == "schedule_checkin"


# ------------------------------------------------ Integration con mocks


@pytest.mark.asyncio
async def test_full_onboarding_flow_completes_planning() -> None:
    """Intake completo → assessment → training → nutrition → schedule_checkin."""
    profile = _make_profile()
    completed_turn = IntakeTurn(
        assistant_message="Listo, gracias.", is_complete=True, validated_responses=[]
    )
    bundle = _make_bundle(intake_turn=completed_turn, profile=profile)
    workflow = build_workflow(bundle)

    state = initial_state("u1")
    state["pending_user_input"] = "Tengo 30, mido 178 y peso 78"

    final = await workflow.ainvoke(state)

    assert final["user_profile"] is not None
    assert final["body_assessment"] is not None
    assert final["current_mesocycle"] is not None
    assert final["current_nutrition_plan"] is not None
    assert final["current_phase"] == "active"
    assert final["next_checkin_date"] is not None
    bundle.intake.process_response.assert_awaited_once()
    bundle.assessment.run.assert_awaited_once()
    bundle.training.run.assert_awaited_once()
    bundle.nutrition.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_intake_partial_yields_back_to_user() -> None:
    """Si la sesión de intake aún no termina, el grafo no avanza a assessment."""
    bundle = _make_bundle()  # turn por defecto: is_complete=False
    workflow = build_workflow(bundle)

    state = initial_state("u1")
    state["pending_user_input"] = "Hola"

    final = await workflow.ainvoke(state)

    assert final["user_profile"] is None
    assert final["current_phase"] == "onboarding"
    assert final["intake_session"] is not None
    bundle.assessment.run.assert_not_awaited()
    bundle.training.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkin_with_adjust_calories_runs_nutrition_only() -> None:
    """Check-in con decisión `adjust_calories`: solo se regenera la nutrición."""
    profile = _make_profile()
    log = _make_progress_log(action="adjust_calories")
    bundle = _make_bundle(profile=profile, progress_log=log)
    workflow = build_workflow(bundle)

    state = initial_state("u1")
    state["current_phase"] = "checkin"
    state["user_profile"] = profile
    state["body_assessment"] = _make_assessment(profile)
    state["current_mesocycle"] = _make_mesocycle()
    state["current_nutrition_plan"] = _make_nutrition_plan()
    state["pending_checkin_data"] = _make_checkin()

    final = await workflow.ainvoke(state)

    assert len(final["progress_logs"]) == 1
    assert final["progress_logs"][-1].decision.action == "adjust_calories"
    bundle.progress.run.assert_awaited_once()
    bundle.nutrition.run.assert_awaited_once()
    bundle.training.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkin_continue_advances_microcycle() -> None:
    """Decisión `continue`: avanza microciclo y reprograma check-in."""
    profile = _make_profile()
    bundle = _make_bundle(profile=profile, progress_log=_make_progress_log(action="continue"))
    workflow = build_workflow(bundle)

    state = initial_state("u1")
    state["current_phase"] = "checkin"
    state["user_profile"] = profile
    state["body_assessment"] = _make_assessment(profile)
    state["current_mesocycle"] = _make_mesocycle(num_micros=4)
    state["current_nutrition_plan"] = _make_nutrition_plan()
    state["current_microcycle_index"] = 0
    state["pending_checkin_data"] = _make_checkin()

    final = await workflow.ainvoke(state)

    assert final["current_microcycle_index"] == 1
    assert final["current_phase"] == "active"
    assert final["next_checkin_date"] is not None
    bundle.training.run.assert_not_awaited()
    bundle.nutrition.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_advance_microcycle_marks_completed_at_end() -> None:
    """Si llegamos al último microciclo, fase pasa a `completed`."""
    profile = _make_profile()
    bundle = _make_bundle(profile=profile, progress_log=_make_progress_log(action="continue"))
    workflow = build_workflow(bundle)

    mesocycle = _make_mesocycle(num_micros=2)
    state = initial_state("u1")
    state["current_phase"] = "checkin"
    state["user_profile"] = profile
    state["body_assessment"] = _make_assessment(profile)
    state["current_mesocycle"] = mesocycle
    state["current_nutrition_plan"] = _make_nutrition_plan()
    state["current_microcycle_index"] = 1  # último (índice 0..1 con 2 microciclos)
    state["pending_checkin_data"] = _make_checkin()

    final = await workflow.ainvoke(state)

    assert final["current_microcycle_index"] == 2
    assert final["current_phase"] == "completed"
