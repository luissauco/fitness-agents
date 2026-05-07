"""Modelos compartidos entre varios módulos para evitar imports circulares.

Aloja `MacroDistribution`, usada por `user_profile`, `body_assessment`,
`nutrition_plan` y `progress_log`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class MacroDistribution(BaseModel):
    """Distribución de macronutrientes y calorías totales del día.

    `calories` es el total declarado y debe ser coherente con
    `protein_g·4 + carbs_g·4 + fat_g·9` (validado en `validators.py`).
    """

    calories: int = Field(..., ge=0, description="Kcal totales del día.")
    protein_g: int = Field(..., ge=0, description="Gramos de proteína.")
    carbs_g: int = Field(..., ge=0, description="Gramos de hidratos.")
    fat_g: int = Field(..., ge=0, description="Gramos de grasa.")
    fiber_g: int | None = Field(default=None, ge=0, description="Gramos de fibra (opcional).")

    @model_validator(mode="after")
    def _non_negative_total(self) -> MacroDistribution:
        """Permite calories=0 (estado vacío) pero rechaza combinaciones imposibles."""
        if self.calories == 0 and (self.protein_g or self.carbs_g or self.fat_g):
            raise ValueError("calories=0 incompatible con macros > 0.")
        return self

    @property
    def protein_kcal(self) -> int:
        """Calorías aportadas por la proteína (4 kcal/g)."""
        return self.protein_g * 4

    @property
    def carbs_kcal(self) -> int:
        """Calorías aportadas por los hidratos (4 kcal/g)."""
        return self.carbs_g * 4

    @property
    def fat_kcal(self) -> int:
        """Calorías aportadas por la grasa (9 kcal/g)."""
        return self.fat_g * 9

    @property
    def protein_pct(self) -> float:
        """% de calorías que aporta la proteína. 0 si calories=0."""
        return (self.protein_kcal / self.calories * 100) if self.calories else 0.0

    @property
    def carbs_pct(self) -> float:
        """% de calorías que aporta el hidrato de carbono."""
        return (self.carbs_kcal / self.calories * 100) if self.calories else 0.0

    @property
    def fat_pct(self) -> float:
        """% de calorías que aporta la grasa."""
        return (self.fat_kcal / self.calories * 100) if self.calories else 0.0
