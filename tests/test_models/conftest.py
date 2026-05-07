"""Fixtures compartidos para los tests de modelos."""

from __future__ import annotations

from datetime import date

import pytest

from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    MetabolicEstimates,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.common import MacroDistribution
from src.models.exercise_db import ExerciseDatabase
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

# ------------------------------------------------------------------ helpers


def _set_scheme(sets: int = 3, rep_lo: int = 8, rep_hi: int = 12, rir: int = 2) -> SetScheme:
    return SetScheme(
        total_sets=sets,
        rep_range=(rep_lo, rep_hi),
        rir=rir,
        description=f"{sets}x{rep_lo}-{rep_hi} (RIR {rir})",
    )


def _programmed(order: int, ex_id: str, name: str) -> ProgrammedExercise:
    return ProgrammedExercise(
        order=order,
        exercise_id=ex_id,
        exercise_name=name,
        set_scheme=_set_scheme(),
    )


def _upper_a(micro_num: int) -> TrainingDay:
    return TrainingDay(
        day_number=1,
        day_label=f"Semana {micro_num} - Upper A",
        exercises=[
            _programmed(1, "press-banca-barra-plano", "Press banca plano"),
            _programmed(2, "remo-barra", "Remo con barra"),
        ],
    )


def _lower_a(micro_num: int) -> TrainingDay:
    return TrainingDay(
        day_number=2,
        day_label=f"Semana {micro_num} - Lower A",
        exercises=[
            _programmed(1, "sentadilla-barra-alta", "Sentadilla barra alta"),
        ],
    )


def _upper_b(micro_num: int) -> TrainingDay:
    return TrainingDay(
        day_number=4,
        day_label=f"Semana {micro_num} - Upper B",
        exercises=[
            _programmed(1, "press-militar-barra", "Press militar barra"),
            _programmed(2, "remo-barra", "Remo con barra"),
        ],
    )


def _lower_b(micro_num: int) -> TrainingDay:
    return TrainingDay(
        day_number=5,
        day_label=f"Semana {micro_num} - Lower B",
        exercises=[
            _programmed(1, "peso-muerto-rumano-barra", "Peso muerto rumano barra"),
        ],
    )


def _rest(day_num: int, micro_num: int) -> TrainingDay:
    return TrainingDay(
        day_number=day_num,
        day_label=f"Semana {micro_num} - Descanso",
        is_rest_day=True,
    )


def _microcycle(number: int, *, is_deload: bool = False) -> Microcycle:
    vol = 0.6 if is_deload else 1.0
    return Microcycle(
        number=number,
        duration_days=7,
        is_deload=is_deload,
        volume_modifier=vol,
        training_days=[
            _upper_a(number),
            _lower_a(number),
            _rest(3, number),
            _upper_b(number),
            _lower_b(number),
            _rest(6, number),
            _rest(7, number),
        ],
    )


def _simple_meal(name: str) -> Meal:
    return Meal(name=name, foods=[FoodItem(name="Pollo a la plancha", amount_g=200.0)])


# ------------------------------------------------------------------ fixtures


@pytest.fixture(scope="session")
def exercise_db() -> ExerciseDatabase:
    return ExerciseDatabase.load()


@pytest.fixture
def training_macros() -> MacroDistribution:
    # protein:175g=700kcal  carbs:215g=860kcal  fat:60g=540kcal  → 2100 kcal exacto
    return MacroDistribution(calories=2100, protein_g=175, carbs_g=215, fat_g=60)


@pytest.fixture
def rest_macros() -> MacroDistribution:
    # protein:175g=700kcal  carbs:150g=600kcal  fat:56g=504kcal  → 1804 kcal (≈1800, Δ=4)
    return MacroDistribution(calories=1800, protein_g=175, carbs_g=150, fat_g=56)


@pytest.fixture
def body_assessment(training_macros: MacroDistribution) -> BodyAssessment:
    return BodyAssessment(
        id="assess-001",
        user_id="user-001",
        date=date(2026, 5, 1),
        measurements=BodyMeasurements(weight_kg=80.0, waist_cm=83.0, hip_cm=96.0),
        visual=VisualAssessment(
            estimated_body_fat_range=(14.0, 17.0),
            fat_distribution="Abdominal predominante.",
            overall_impression="Físico atlético con margen de mejora en zona abdominal.",
        ),
        metabolic=MetabolicEstimates.from_basic_data(
            weight_kg=80.0,
            height_cm=178.0,
            age=28,
            sex="M",
            activity_factor=1.55,
            waist_cm=83.0,
            hip_cm=96.0,
        ),
        phase_recommendation=PhaseRecommendation(
            recommended_phase="minicut",
            reasoning="BF estimado 14-17 %; deficit moderado para bajar a 12-14 %.",
            suggested_duration_weeks=6,
            suggested_calorie_target=2100,
            suggested_macros=training_macros,
        ),
    )


@pytest.fixture
def mesocycle() -> Mesocycle:
    return Mesocycle(
        id="meso-001",
        user_id="user-001",
        name="Hipertrofia Upper/Lower 4 microciclos",
        start_date=date(2026, 5, 5),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[
            _microcycle(1),
            _microcycle(2),
            _microcycle(3),
            _microcycle(4, is_deload=True),
        ],
        weekly_schedule=WeeklySchedule(
            days=[
                {"day": 1, "type": "upper", "steps": 10000},
                {"day": 2, "type": "lower", "steps": 10000},
                {"day": 3, "type": "descanso", "steps": 12000},
                {"day": 4, "type": "upper", "steps": 10000},
                {"day": 5, "type": "lower", "steps": 10000},
                {"day": 6, "type": "descanso", "steps": 12000},
                {"day": 7, "type": "descanso", "steps": 12000},
            ]
        ),
        progression_strategy="+1 serie/semana hasta micro 3; micro 4 descarga (-40% volumen).",
    )


@pytest.fixture
def nutrition_plan(
    training_macros: MacroDistribution, rest_macros: MacroDistribution
) -> NutritionPlan:
    return NutritionPlan(
        id="plan-001",
        user_id="user-001",
        name="Plan Minicut Mayo 2026",
        objective="Perder grasa preservando masa muscular.",
        phase="minicut",
        duration="4 semanas",
        start_date=date(2026, 5, 5),
        training_day_diet=DailyDiet(
            day_type="training",
            macros=training_macros,
            meals=[
                _simple_meal("Desayuno"),
                _simple_meal("Comida"),
                _simple_meal("Cena"),
            ],
            supplements=["creatina 5g", "whey 30g post-entreno"],
        ),
        rest_day_diet=DailyDiet(
            day_type="rest",
            macros=rest_macros,
            meals=[
                _simple_meal("Desayuno"),
                _simple_meal("Comida"),
                _simple_meal("Cena"),
            ],
        ),
        interchange_rules=InterchangeRules(
            carb_sources={"100g arroz cocido": "400g patata cocida"},
            protein_sources=["pechuga pollo", "atún al natural", "claras de huevo"],
            vegetable_rule="Verduras verdes ad libitum.",
            fruit_rule="1 pieza mediana máx/día.",
        ),
        general_tips=GeneralTips(
            tips=["Pesar alimentos en crudo.", "Cocinar con spray de aceite."],
            allowed_drinks=["agua", "café sin azúcar", "té"],
            sauce_rule="Solo salsas 0 kcal.",
            seasoning_notes="Especias sin restricción.",
        ),
        neat_cardio_notes="8.000 pasos mínimos/día. Sin cardio estructurado.",
    )
