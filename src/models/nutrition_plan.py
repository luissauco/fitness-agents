"""Plan nutricional: dietas para días de entreno y descanso, reglas de intercambio.

`NutritionPlan` es el modelo que consume el generador de PDFs nutricionales
y el agente nutricionista para validar/ajustar las kcal y macros del usuario.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.models.common import MacroDistribution


class FoodItem(BaseModel):
    """Un alimento dentro de una comida, con sus alternativas intercambiables."""

    name: str
    amount_g: float = Field(..., gt=0, description="Cantidad en gramos.")
    alternatives: list[str] = Field(
        default_factory=list, description="Alimentos intercambiables (ej: 'pasta', 'quinoa')."
    )
    alternative_amounts: list[str] = Field(
        default_factory=list,
        description=(
            "Cantidades de las alternativas, paralelas a `alternatives` "
            "(ej: '180gr de patata cocida')."
        ),
    )
    preparation_notes: str | None = Field(
        default=None, description="Forma de preparación (al horno, plancha, vapor…)."
    )
    is_optional: bool = False

    @model_validator(mode="after")
    def _alternatives_consistency(self) -> FoodItem:
        """Si hay `alternative_amounts`, debe haber el mismo nº que `alternatives`."""
        if self.alternative_amounts and len(self.alternative_amounts) != len(self.alternatives):
            raise ValueError(
                "`alternative_amounts` debe tener la misma longitud que `alternatives` "
                "(o estar vacío)."
            )
        return self


class Meal(BaseModel):
    """Una comida del día (Desayuno, Comida, Cena, Intraentreno…)."""

    name: str
    time_suggestion: str | None = Field(
        default=None, description="Hora sugerida en texto libre (ej: '07:30', 'pre-entreno')."
    )
    foods: list[FoodItem] = Field(..., min_length=1)
    notes: str | None = None
    is_intra_workout: bool = False


class DailyDiet(BaseModel):
    """Dieta para un tipo de día (entreno o descanso)."""

    day_type: Literal["training", "rest"]
    macros: MacroDistribution
    meals: list[Meal] = Field(..., min_length=1)
    supplements: list[str] = Field(
        default_factory=list,
        description="Suplementos del día (ej: 'creatina 5g', 'whey 30g post-entreno').",
    )


class CheatMealProtocol(BaseModel):
    """Protocolo de comida libre / cheat meal."""

    strategy: str = Field(..., description="Estrategia general (frecuencia, timing, criterios).")
    pre_cheat_tips: list[str] = Field(default_factory=list)
    day_structure: list[str] = Field(
        default_factory=list, description="Estructura del día con cheat (ayuno previo, etc.)."
    )
    frequency: str = Field(..., description="Frecuencia sugerida (ej: '1 vez cada 14 días').")


class InterchangeRules(BaseModel):
    """Reglas de intercambiabilidad de alimentos.

    `carb_sources` mapea una porción de referencia a su equivalente
    (ej: `'100g arroz cocido'` → `'450g patata cocida'`).
    """

    carb_sources: dict[str, str] = Field(default_factory=dict)
    protein_sources: list[str] = Field(
        default_factory=list,
        description="Fuentes proteicas intercambiables a igualdad de gramos.",
    )
    vegetable_rule: str = Field(..., description="Regla general para verduras.")
    fruit_rule: str = Field(
        ..., description="Regla para frutas (cantidades equivalentes, excepciones)."
    )
    notes: list[str] = Field(default_factory=list)


class GeneralTips(BaseModel):
    """Tips generales y reglas globales del plan."""

    tips: list[str] = Field(default_factory=list)
    allowed_drinks: list[str] = Field(
        default_factory=list, description="Bebidas acalóricas permitidas en cualquier momento."
    )
    sauce_rule: str = Field(..., description="Regla aplicable a salsas (siempre 0 kcal, etc.).")
    seasoning_notes: str = Field(..., description="Condimentos/especias permitidos.")


class NutritionPlan(BaseModel):
    """Plan nutricional completo con plantillas de entreno/descanso."""

    id: str
    user_id: str
    name: str = Field(..., description="Nombre legible (ej: 'Plan Minicut Mayo 2026').")
    objective: str = Field(..., description="Descripción del objetivo de la fase.")
    phase: Literal["cut", "minicut", "maintenance", "lean_bulk", "bulk", "recomposition"]
    duration: str = Field(..., description="Duración prevista (ej: '1 mesociclo', '12 semanas').")
    start_date: date
    training_day_diet: DailyDiet
    rest_day_diet: DailyDiet
    interchange_rules: InterchangeRules
    cheat_meal_protocol: CheatMealProtocol | None = None
    general_tips: GeneralTips
    neat_cardio_notes: str = Field(
        ..., description="Pautas de NEAT y cardio LISS (pasos, sesiones, intensidad)."
    )
    created_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def _check_day_types(self) -> NutritionPlan:
        """Las dos plantillas deben llevar el `day_type` correcto."""
        if self.training_day_diet.day_type != "training":
            raise ValueError("`training_day_diet.day_type` debe ser 'training'.")
        if self.rest_day_diet.day_type != "rest":
            raise ValueError("`rest_day_diet.day_type` debe ser 'rest'.")
        return self

    @property
    def calorie_difference(self) -> int:
        """Diferencia de kcal entre día de entreno y descanso (positiva si entreno > descanso)."""
        return self.training_day_diet.macros.calories - self.rest_day_diet.macros.calories
