"""Fixtures con datos estáticos (sin LLM) para los tests de generadores."""

from __future__ import annotations

from datetime import date

import pytest

from src.models.body_assessment import BodyMeasurements
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
    CheatMealProtocol,
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

# ------------------------------------------------------------- mesocycle


def _scheme(sets: int = 3, lo: int = 8, hi: int = 12, rir: int = 2) -> SetScheme:
    return SetScheme(
        total_sets=sets,
        rep_range=(lo, hi),
        rir=rir,
        rest_seconds=150,
        description=f"{sets}x{lo}-{hi} (RIR {rir})",
    )


def _top_back_off() -> SetScheme:
    return SetScheme(
        total_sets=3,
        rep_range=(5, 8),
        rir=1,
        technique="top_back_off",
        top_set_count=1,
        backoff_set_count=2,
        rest_seconds=180,
        description="top: 1x5(1) / back-off: 2x8(1)",
    )


def _ex(
    order: int, ex_id: str, name: str, *, top: bool = False, note: str | None = None
) -> ProgrammedExercise:
    return ProgrammedExercise(
        order=order,
        exercise_id=ex_id,
        exercise_name=name,
        set_scheme=_top_back_off() if top else _scheme(),
        progression_notes=note,
    )


def _upper(micro: int) -> TrainingDay:
    return TrainingDay(
        day_number=1,
        day_label=f"Semana {micro} - Día 1 - Upper",
        exercises=[
            _ex(
                1,
                "press-banca-barra-plano",
                "Press banca plano",
                top=True,
                note="banco plano, agarre medio, ROM completo",
            ),
            _ex(2, "remo-barra", "Remo con barra"),
        ],
    )


def _lower(micro: int) -> TrainingDay:
    return TrainingDay(
        day_number=2,
        day_label=f"Semana {micro} - Día 2 - Lower",
        exercises=[_ex(1, "sentadilla-barra-alta", "Sentadilla barra alta")],
    )


def _rest_day(num: int, micro: int) -> TrainingDay:
    return TrainingDay(
        day_number=num,
        day_label=f"Semana {micro} - Día {num} - Descanso",
        is_rest_day=True,
    )


def _micro(number: int, *, deload: bool = False) -> Microcycle:
    return Microcycle(
        number=number,
        duration_days=7,
        is_deload=deload,
        volume_modifier=0.6 if deload else 1.0,
        training_days=[
            _upper(number),
            _lower(number),
            _rest_day(3, number),
            _upper(number),
            _lower(number),
            _rest_day(6, number),
            _rest_day(7, number),
        ],
    )


@pytest.fixture
def mesocycle() -> Mesocycle:
    """Mesociclo Upper/Lower con 3 micros + 1 descarga, 4 días/semana."""
    return Mesocycle(
        id="meso-001",
        user_id="user-001",
        name="Hipertrofia Upper/Lower 4 microciclos",
        start_date=date(2026, 5, 5),
        phase="hypertrophy",
        split_type="upper_lower",
        training_days_per_week=4,
        microcycles=[
            _micro(1),
            _micro(2),
            _micro(3),
            _micro(4, deload=True),
        ],
        weekly_schedule=WeeklySchedule(
            days=[
                {"day": 1, "type": "pesas", "steps": 10000},
                {"day": 2, "type": "pesas", "steps": 10000},
                {"day": 3, "type": "descanso", "steps": 12000},
                {"day": 4, "type": "pesas", "steps": 10000},
                {"day": 5, "type": "pesas", "steps": 10000},
                {"day": 6, "type": "descanso", "steps": 12000},
                {"day": 7, "type": "descanso", "steps": 12000},
            ]
        ),
        progression_strategy="+1 serie/semana hasta micro 3; micro 4 descarga (-40% volumen).",
        notes="Priorizar técnica y progresión de cargas conservadora.",
    )


# ------------------------------------------------------------- nutrition


def _meal(name: str) -> Meal:
    return Meal(
        name=name,
        time_suggestion="08:00",
        foods=[
            FoodItem(
                name="Avena",
                amount_g=80.0,
                alternatives=["pan integral"],
                alternative_amounts=["70gr de pan integral"],
                preparation_notes="con leche desnatada",
            ),
            FoodItem(name="Claras de huevo", amount_g=200.0),
        ],
    )


@pytest.fixture
def nutrition_plan() -> NutritionPlan:
    """Plan nutricional minicut completo."""
    training_macros = MacroDistribution(calories=2100, protein_g=175, carbs_g=215, fat_g=60)
    rest_macros = MacroDistribution(calories=1800, protein_g=175, carbs_g=150, fat_g=56)
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
            meals=[_meal("Desayuno"), _meal("Comida"), _meal("Cena")],
            supplements=["creatina 5g", "whey 30g post-entreno"],
        ),
        rest_day_diet=DailyDiet(
            day_type="rest",
            macros=rest_macros,
            meals=[_meal("Desayuno"), _meal("Comida"), _meal("Cena")],
        ),
        interchange_rules=InterchangeRules(
            carb_sources={"100g arroz cocido": "400g patata cocida"},
            protein_sources=["pechuga pollo", "atún al natural", "claras de huevo"],
            vegetable_rule="Verduras verdes ad libitum.",
            fruit_rule="1 pieza mediana máx/día.",
        ),
        cheat_meal_protocol=CheatMealProtocol(
            strategy="Una comida libre cada 14 días, preferible post-entreno.",
            pre_cheat_tips=["Entrenar ese día", "Mantener proteína alta"],
            day_structure=["Desayuno normal", "Comida libre", "Cena ligera"],
            frequency="1 vez cada 14 días",
        ),
        general_tips=GeneralTips(
            tips=["Pesar alimentos en crudo.", "Cocinar con spray de aceite."],
            allowed_drinks=["agua", "café sin azúcar", "té"],
            sauce_rule="Solo salsas 0 kcal.",
            seasoning_notes="Especias sin restricción.",
        ),
        neat_cardio_notes="8.000 pasos mínimos/día. 2 sesiones LISS de 30' opcionales.",
    )


# ------------------------------------------------------------- progress


@pytest.fixture
def progress_log() -> ProgressLog:
    """Check-in bisemanal con tendencia positiva."""
    return ProgressLog(
        id="log-001",
        user_id="user-001",
        mesocycle_id="meso-001",
        microcycle_number=2,
        date=date(2026, 5, 19),
        period_start=date(2026, 5, 5),
        period_end=date(2026, 5, 19),
        weight=WeightLog.from_weights([80.0, 79.6, 79.2, 78.9], last_average=80.5),
        measurements=BodyMeasurements(weight_kg=78.9, waist_cm=81.0, hip_cm=95.0),
        training=TrainingProgress(
            exercises_tracked=8,
            exercises_progressed=5,
            exercises_stagnated=2,
            exercises_regressed=1,
            volume_adherence_pct=92.0,
            notable_prs=["Press banca 80kg x6", "Sentadilla 110kg x5"],
            problem_exercises=["Remo con barra (molestia lumbar)"],
        ),
        nutrition=NutritionAdherence(
            adherence_pct=88.0,
            cheat_meals_count=1,
            missed_meals_avg=0.3,
            supplement_adherence=True,
            water_intake_liters=3.0,
            notes="Buena adherencia general, algún desliz el fin de semana.",
        ),
        subjective=SubjectiveFeedback(
            energy_level=7,
            sleep_quality=6,
            hunger_level=6,
            motivation=8,
            stress_level=4,
            soreness=5,
            mood=8,
            pain_or_discomfort="Ligera molestia lumbar en remo.",
            additional_notes="En general buenas sensaciones.",
        ),
        daily_steps_avg=10500,
        decision=ProgressDecision(
            action="continue",
            reasoning="Pérdida de grasa en buen rango y fuerza en progresión.",
            details={"weekly_loss_kg": 0.45},
        ),
        report_summary=(
            "Periodo positivo: -1.6 kg de media, fuerza al alza y buena adherencia. "
            "Se mantiene el plan actual."
        ),
    )
