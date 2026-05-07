"""Tests de las funciones de validación cruzada entre modelos."""

from __future__ import annotations

from datetime import date

from src.models.body_assessment import BodyAssessment
from src.models.common import MacroDistribution
from src.models.exercise_db import Equipment, ExerciseDatabase
from src.models.mesocycle import Mesocycle, Microcycle, TrainingDay, WeeklySchedule
from src.models.nutrition_plan import DailyDiet, NutritionPlan
from src.models.validators import (
    validate_equipment_compatibility,
    validate_macros_consistency,
    validate_mesocycle_structure,
    validate_nutrition_vs_assessment,
)
from tests.test_models.conftest import _microcycle, _simple_meal

# ----------------------------------------------------------- validate_macros_consistency


def test_macros_consistency_exact_match() -> None:
    # 175*4 + 215*4 + 60*9 = 700 + 860 + 540 = 2100
    macros = MacroDistribution(calories=2100, protein_g=175, carbs_g=215, fat_g=60)
    assert validate_macros_consistency(macros) is True


def test_macros_consistency_within_tolerance() -> None:
    # delta=4 kcal (dentro de ±50)
    macros = MacroDistribution(calories=1800, protein_g=175, carbs_g=150, fat_g=56)
    assert validate_macros_consistency(macros) is True


def test_macros_consistency_out_of_tolerance() -> None:
    # 175*4 + 215*4 + 60*9 = 2100, pero declaramos 2200 → delta=100 > 50
    macros = MacroDistribution(calories=2200, protein_g=175, carbs_g=215, fat_g=60)
    assert validate_macros_consistency(macros) is False


# ----------------------------------------------------------- validate_mesocycle_structure


def test_mesocycle_structure_valid(mesocycle: Mesocycle) -> None:
    warnings = validate_mesocycle_structure(mesocycle)
    assert warnings == []


def test_mesocycle_structure_no_deload_warns() -> None:
    meso = Mesocycle(
        id="meso-test",
        user_id="u1",
        name="Sin descarga",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[_microcycle(1), _microcycle(2)],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="lineal",
    )
    warnings = validate_mesocycle_structure(meso)
    assert any("descarga" in w.lower() for w in warnings)


def test_mesocycle_structure_bad_numbering_warns() -> None:
    m1 = _microcycle(1)
    m3 = _microcycle(3)  # salta el número 2
    m4 = _microcycle(4, is_deload=True)
    meso = Mesocycle(
        id="meso-test",
        user_id="u1",
        name="Numeración incorrecta",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[m1, m3, m4],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="lineal",
    )
    warnings = validate_mesocycle_structure(meso)
    assert any("secuencial" in w for w in warnings)


def test_mesocycle_structure_deload_not_last_warns() -> None:
    meso = Mesocycle(
        id="meso-test",
        user_id="u1",
        name="Descarga al inicio",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[
            _microcycle(1, is_deload=True),  # descarga al inicio
            _microcycle(2),
        ],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="lineal",
    )
    warnings = validate_mesocycle_structure(meso)
    assert any("último" in w for w in warnings)


def test_mesocycle_structure_empty_training_day_warns() -> None:
    micro = Microcycle(
        number=1,
        duration_days=7,
        is_deload=True,
        training_days=[
            TrainingDay(day_number=1, day_label="Día 1 sin ejercicios"),  # active, no exercises
            *[
                TrainingDay(day_number=i, day_label=f"Descanso {i}", is_rest_day=True)
                for i in range(2, 8)
            ],
        ],
    )
    meso = Mesocycle(
        id="meso-test",
        user_id="u1",
        name="Día vacío",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=1,
        microcycles=[micro],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="lineal",
    )
    warnings = validate_mesocycle_structure(meso)
    assert any("sin ejercicios" in w for w in warnings)


# ----------------------------------------------------------- validate_nutrition_vs_assessment


def test_nutrition_vs_assessment_valid(
    nutrition_plan: NutritionPlan,
    body_assessment: BodyAssessment,
) -> None:
    warnings = validate_nutrition_vs_assessment(nutrition_plan, body_assessment)
    assert warnings == []


def test_nutrition_vs_assessment_phase_mismatch(
    nutrition_plan: NutritionPlan,
    body_assessment: BodyAssessment,
) -> None:
    data = nutrition_plan.model_dump()
    data["phase"] = "lean_bulk"  # distinto de la recomendación "minicut"
    plan = NutritionPlan.model_validate(data)
    warnings = validate_nutrition_vs_assessment(plan, body_assessment)
    assert any("Fase" in w for w in warnings)


def test_nutrition_vs_assessment_kcal_deviation_warns(
    body_assessment: BodyAssessment,
    rest_macros: MacroDistribution,
) -> None:
    # Macros de entrenamiento con 1600 kcal (desviación > 200 respecto al objetivo 2100)
    low_macros = MacroDistribution(calories=1600, protein_g=175, carbs_g=95, fat_g=60)
    plan = NutritionPlan(
        id="plan-bad",
        user_id="user-001",
        name="Plan desviado",
        objective="Test",
        phase="minicut",
        duration="4 semanas",
        start_date=date(2026, 5, 5),
        training_day_diet=DailyDiet(
            day_type="training",
            macros=low_macros,
            meals=[_simple_meal("Comida")],
        ),
        rest_day_diet=DailyDiet(
            day_type="rest",
            macros=rest_macros,
            meals=[_simple_meal("Comida")],
        ),
        interchange_rules=__import__(
            "src.models.nutrition_plan", fromlist=["InterchangeRules"]
        ).InterchangeRules(
            carb_sources={},
            protein_sources=[],
            vegetable_rule="Ad libitum.",
            fruit_rule="1 pieza/día.",
        ),
        general_tips=__import__("src.models.nutrition_plan", fromlist=["GeneralTips"]).GeneralTips(
            sauce_rule="0 kcal.",
            seasoning_notes="Libre.",
            allowed_drinks=["agua"],
        ),
        neat_cardio_notes="8k pasos.",
    )
    warnings = validate_nutrition_vs_assessment(plan, body_assessment)
    assert any("kcal" in w for w in warnings)


def test_nutrition_vs_assessment_rest_exceeds_training_warns(
    body_assessment: BodyAssessment,
    training_macros: MacroDistribution,
) -> None:
    high_rest = MacroDistribution(calories=2500, protein_g=175, carbs_g=295, fat_g=60)
    from src.models.nutrition_plan import GeneralTips, InterchangeRules

    plan = NutritionPlan(
        id="plan-rest-high",
        user_id="user-001",
        name="Plan descanso alto",
        objective="Test",
        phase="minicut",
        duration="4 semanas",
        start_date=date(2026, 5, 5),
        training_day_diet=DailyDiet(
            day_type="training",
            macros=training_macros,
            meals=[_simple_meal("Comida")],
        ),
        rest_day_diet=DailyDiet(
            day_type="rest",
            macros=high_rest,
            meals=[_simple_meal("Comida")],
        ),
        interchange_rules=InterchangeRules(
            carb_sources={},
            protein_sources=[],
            vegetable_rule="Ad libitum.",
            fruit_rule="1 pieza/día.",
        ),
        general_tips=GeneralTips(
            sauce_rule="0 kcal.",
            seasoning_notes="Libre.",
            allowed_drinks=["agua"],
        ),
        neat_cardio_notes="8k pasos.",
    )
    warnings = validate_nutrition_vs_assessment(plan, body_assessment)
    assert any("descanso" in w.lower() for w in warnings)


# ----------------------------------------------------------- validate_equipment_compatibility


def test_equipment_compatibility_full_gym_passes(
    mesocycle: Mesocycle,
    exercise_db: ExerciseDatabase,
) -> None:
    available = [Equipment.BARBELL, Equipment.BENCH, Equipment.PULLUP_BAR, Equipment.DUMBBELL]
    warnings = validate_equipment_compatibility(mesocycle, available, database=exercise_db)
    assert warnings == []


def test_equipment_compatibility_missing_equipment_warns(
    mesocycle: Mesocycle,
    exercise_db: ExerciseDatabase,
) -> None:
    # Sin barra: todos los ejercicios del mesociclo necesitan barbell
    available = [Equipment.DUMBBELL]
    warnings = validate_equipment_compatibility(mesocycle, available, database=exercise_db)
    assert len(warnings) > 0


def test_equipment_compatibility_unknown_exercise_warns(
    exercise_db: ExerciseDatabase,
) -> None:
    from src.models.mesocycle import ProgrammedExercise, SetScheme

    micro = Microcycle(
        number=1,
        duration_days=7,
        is_deload=True,
        training_days=[
            TrainingDay(
                day_number=1,
                day_label="Día 1",
                exercises=[
                    ProgrammedExercise(
                        order=1,
                        exercise_id="ejercicio-no-existe",
                        exercise_name="Ejercicio inventado",
                        set_scheme=SetScheme(
                            total_sets=3, rep_range=(8, 12), rir=2, description="3x8-12"
                        ),
                    )
                ],
            ),
            *[
                TrainingDay(day_number=i, day_label=f"Descanso {i}", is_rest_day=True)
                for i in range(2, 8)
            ],
        ],
    )
    meso = Mesocycle(
        id="meso-unk",
        user_id="u1",
        name="Con ejercicio desconocido",
        start_date=date(2026, 5, 1),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=1,
        microcycles=[micro],
        weekly_schedule=WeeklySchedule(),
        progression_strategy="lineal",
    )
    warnings = validate_equipment_compatibility(meso, [Equipment.BARBELL], database=exercise_db)
    assert any("no existe" in w for w in warnings)
