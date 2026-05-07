"""Tests del plan nutricional: macros, días y reglas de intercambio."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.common import MacroDistribution
from src.models.nutrition_plan import (
    DailyDiet,
    FoodItem,
    Meal,
    NutritionPlan,
)

# ----------------------------------------------------------- MacroDistribution


def test_macro_kcal_properties(training_macros: MacroDistribution) -> None:
    assert training_macros.protein_kcal == 175 * 4
    assert training_macros.carbs_kcal == 215 * 4
    assert training_macros.fat_kcal == 60 * 9


def test_macro_kcal_sum_matches_calories(training_macros: MacroDistribution) -> None:
    total = training_macros.protein_kcal + training_macros.carbs_kcal + training_macros.fat_kcal
    assert total == training_macros.calories


def test_macro_pct_sums_to_100(training_macros: MacroDistribution) -> None:
    total_pct = training_macros.protein_pct + training_macros.carbs_pct + training_macros.fat_pct
    assert abs(total_pct - 100.0) < 0.1


def test_calories_zero_with_macros_raises() -> None:
    with pytest.raises(ValidationError):
        MacroDistribution(calories=0, protein_g=50, carbs_g=0, fat_g=0)


# ----------------------------------------------------------- FoodItem


def test_food_item_alternatives_length_mismatch_raises() -> None:
    with pytest.raises(ValidationError):
        FoodItem(
            name="Arroz",
            amount_g=100.0,
            alternatives=["patata", "pasta"],
            alternative_amounts=["400g"],  # longitud 1 ≠ 2
        )


def test_food_item_no_alternatives_valid() -> None:
    item = FoodItem(name="Pollo", amount_g=200.0)
    assert item.alternatives == []
    assert item.alternative_amounts == []


def test_food_item_parallel_alternatives_valid() -> None:
    item = FoodItem(
        name="Arroz",
        amount_g=100.0,
        alternatives=["patata", "pasta"],
        alternative_amounts=["400g patata cocida", "80g pasta seca"],
    )
    assert len(item.alternatives) == len(item.alternative_amounts)


# ----------------------------------------------------------- NutritionPlan


def test_calorie_difference(nutrition_plan: NutritionPlan) -> None:
    diff = nutrition_plan.calorie_difference
    expected = (
        nutrition_plan.training_day_diet.macros.calories
        - nutrition_plan.rest_day_diet.macros.calories
    )
    assert diff == expected
    assert diff > 0  # minicut: entreno > descanso


def test_day_type_validator_training_marked_correctly(nutrition_plan: NutritionPlan) -> None:
    assert nutrition_plan.training_day_diet.day_type == "training"


def test_day_type_validator_rest_marked_correctly(nutrition_plan: NutritionPlan) -> None:
    assert nutrition_plan.rest_day_diet.day_type == "rest"


def test_wrong_training_day_type_raises(nutrition_plan: NutritionPlan) -> None:
    bad_data = nutrition_plan.model_dump()
    bad_data["training_day_diet"]["day_type"] = "rest"
    with pytest.raises(ValidationError):
        NutritionPlan.model_validate(bad_data)


def test_wrong_rest_day_type_raises(nutrition_plan: NutritionPlan) -> None:
    bad_data = nutrition_plan.model_dump()
    bad_data["rest_day_diet"]["day_type"] = "training"
    with pytest.raises(ValidationError):
        NutritionPlan.model_validate(bad_data)


def test_meal_requires_at_least_one_food() -> None:
    with pytest.raises(ValidationError):
        Meal(name="Desayuno", foods=[])


def test_daily_diet_requires_at_least_one_meal(training_macros: MacroDistribution) -> None:
    with pytest.raises(ValidationError):
        DailyDiet(day_type="training", macros=training_macros, meals=[])
