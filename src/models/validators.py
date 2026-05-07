"""Validaciones cruzadas entre modelos.

Cada función devuelve `True/False` (consistencia binaria) o una lista de
warnings legibles que el agente puede usar para corregir.
"""

from __future__ import annotations

from src.models.body_assessment import BodyAssessment
from src.models.common import MacroDistribution
from src.models.exercise_db import Equipment, ExerciseDatabase
from src.models.mesocycle import Mesocycle
from src.models.nutrition_plan import NutritionPlan

# Tolerancia entre kcal declaradas y kcal calculadas a partir de los macros.
_MACRO_KCAL_TOLERANCE: int = 50

# Tolerancia entre kcal del plan y kcal sugeridas por la evaluación.
_PLAN_VS_RECO_TOLERANCE: int = 200


def validate_macros_consistency(macros: MacroDistribution) -> bool:
    """`protein·4 + carbs·4 + fat·9 ≈ calories` (±`_MACRO_KCAL_TOLERANCE` kcal).

    Devuelve `True` si la suma de macros es consistente con el total declarado.
    """
    computed: int = macros.protein_kcal + macros.carbs_kcal + macros.fat_kcal
    return abs(computed - macros.calories) <= _MACRO_KCAL_TOLERANCE


def validate_mesocycle_structure(mesocycle: Mesocycle) -> list[str]:
    """Devuelve una lista de warnings sobre la coherencia estructural del mesociclo.

    Comprueba:
        - Numeración secuencial de microciclos (1, 2, 3...).
        - Existencia de descarga.
        - La descarga es el último microciclo (recomendado).
        - Cada microciclo tiene `len(training_days)` ≈ `training_days_per_week`.
        - Cada training day no de descanso tiene al menos un ejercicio.
        - Numeración secuencial de `day_number` dentro de cada microciclo.
    """
    warnings: list[str] = []

    expected: int = 1
    for m in mesocycle.microcycles:
        if m.number != expected:
            warnings.append(
                f"Microciclo en posición {expected} tiene number={m.number} "
                "(numeración no secuencial)."
            )
        expected += 1

    deload_indices: list[int] = [i for i, m in enumerate(mesocycle.microcycles) if m.is_deload]
    if not deload_indices:
        warnings.append("El mesociclo no contiene ningún microciclo de descarga.")
    elif deload_indices[-1] != len(mesocycle.microcycles) - 1:
        warnings.append(
            "La descarga no es el último microciclo (suele recomendarse colocarla al final)."
        )

    target_days: int = mesocycle.training_days_per_week
    for m in mesocycle.microcycles:
        actual_training: int = sum(1 for d in m.training_days if not d.is_rest_day)
        if actual_training != target_days:
            warnings.append(
                f"Microciclo {m.number}: {actual_training} días de entreno "
                f"(esperado {target_days})."
            )

        seen_day_numbers: set[int] = set()
        for d in m.training_days:
            if d.day_number in seen_day_numbers:
                warnings.append(f"Microciclo {m.number}: day_number={d.day_number} duplicado.")
            seen_day_numbers.add(d.day_number)
            if not d.is_rest_day and not d.exercises:
                warnings.append(
                    f"Microciclo {m.number}, {d.day_label}: día de entreno sin ejercicios."
                )

    return warnings


def validate_nutrition_vs_assessment(plan: NutritionPlan, assessment: BodyAssessment) -> list[str]:
    """Comprueba que el plan nutricional es coherente con la fase recomendada.

    Devuelve warnings si:
        - La fase del plan no coincide con la sugerida.
        - Las kcal del día de entreno se desvían >`_PLAN_VS_RECO_TOLERANCE` kcal
          del objetivo sugerido.
        - Las kcal del día de descanso son mayores que las del día de entreno
          (típicamente al revés en hipertrofia/recomp).
        - Las plantillas no son consistentes con `validate_macros_consistency`.
    """
    warnings: list[str] = []
    reco = assessment.phase_recommendation

    if plan.phase != reco.recommended_phase:
        warnings.append(
            f"Fase del plan ('{plan.phase}') distinta de la recomendada "
            f"('{reco.recommended_phase}')."
        )

    train_kcal: int = plan.training_day_diet.macros.calories
    if abs(train_kcal - reco.suggested_calorie_target) > _PLAN_VS_RECO_TOLERANCE:
        warnings.append(
            f"kcal entreno del plan ({train_kcal}) desvían más de "
            f"{_PLAN_VS_RECO_TOLERANCE} de las sugeridas ({reco.suggested_calorie_target})."
        )

    rest_kcal: int = plan.rest_day_diet.macros.calories
    if rest_kcal > train_kcal:
        warnings.append(
            f"kcal en día de descanso ({rest_kcal}) > día de entreno ({train_kcal}); "
            "suele ser al revés."
        )

    if not validate_macros_consistency(plan.training_day_diet.macros):
        warnings.append(
            "Macros del día de entreno no cuadran con calories declaradas "
            f"(±{_MACRO_KCAL_TOLERANCE} kcal)."
        )
    if not validate_macros_consistency(plan.rest_day_diet.macros):
        warnings.append(
            "Macros del día de descanso no cuadran con calories declaradas "
            f"(±{_MACRO_KCAL_TOLERANCE} kcal)."
        )

    return warnings


def validate_equipment_compatibility(
    mesocycle: Mesocycle,
    available: list[Equipment],
    *,
    database: ExerciseDatabase | None = None,
) -> list[str]:
    """Verifica que todos los ejercicios del mesociclo se pueden ejecutar.

    Para cada ejercicio programado consulta el catálogo y comprueba que su
    `equipment` es subconjunto del `available`. Devuelve un warning por
    ejercicio incompatible y otro por id desconocido.
    """
    db: ExerciseDatabase = database or ExerciseDatabase.load()
    available_set: set[Equipment] = set(available)
    warnings: list[str] = []
    seen_unknown: set[str] = set()

    for m in mesocycle.microcycles:
        for d in m.training_days:
            for pe in d.exercises:
                ex = db.by_id(pe.exercise_id)
                if ex is None:
                    if pe.exercise_id not in seen_unknown:
                        warnings.append(
                            f"Ejercicio '{pe.exercise_id}' (Micro {m.number}, "
                            f"{d.day_label}) no existe en el catálogo."
                        )
                        seen_unknown.add(pe.exercise_id)
                    continue
                missing: set[Equipment] = set(ex.equipment) - available_set
                if missing:
                    warnings.append(
                        f"'{ex.name}' (Micro {m.number}, {d.day_label}) requiere "
                        f"{sorted(e.value for e in missing)} no disponible."
                    )

    return warnings
