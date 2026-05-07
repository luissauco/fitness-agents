"""Evaluación corporal: medidas, lectura visual, metabolismo y fase recomendada.

Modelos usados por el agente evaluador para registrar la composición corporal
inicial (y posteriores reevaluaciones) del usuario.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator

from src.models.common import MacroDistribution

# ---------------------------------------------------------------- Medidas


class BodyMeasurements(BaseModel):
    """Medidas corporales en cm. Solo `weight_kg` es obligatorio."""

    weight_kg: float = Field(..., gt=0)
    waist_cm: float | None = Field(default=None, gt=0)
    hip_cm: float | None = Field(default=None, gt=0)
    chest_cm: float | None = Field(default=None, gt=0)
    arm_left_cm: float | None = Field(default=None, gt=0)
    arm_right_cm: float | None = Field(default=None, gt=0)
    thigh_left_cm: float | None = Field(default=None, gt=0)
    thigh_right_cm: float | None = Field(default=None, gt=0)
    calf_left_cm: float | None = Field(default=None, gt=0)
    calf_right_cm: float | None = Field(default=None, gt=0)
    neck_cm: float | None = Field(default=None, gt=0)
    shoulder_cm: float | None = Field(default=None, gt=0)


# ---------------------------------------------------------- Lectura visual

# Niveles de desarrollo muscular usados en `VisualAssessment.muscle_development`.
MuscleDevelopmentLevel = Literal["underdeveloped", "average", "developed", "strong"]


class VisualAssessment(BaseModel):
    """Lectura visual del físico, generada por Claude Vision sobre las fotos."""

    estimated_body_fat_range: tuple[float, float] = Field(
        ..., description="Rango estimado de % graso (low, high)."
    )
    fat_distribution: str = Field(
        ..., description="Descripción de la distribución de grasa (abdominal, glútea, etc.)."
    )
    muscle_development: dict[str, MuscleDevelopmentLevel] = Field(
        default_factory=dict,
        description="Mapa grupo muscular → nivel de desarrollo observado.",
    )
    weak_points: list[str] = Field(
        default_factory=list, description="Grupos musculares con menos desarrollo relativo."
    )
    strong_points: list[str] = Field(
        default_factory=list, description="Grupos musculares con más desarrollo relativo."
    )
    posture_notes: str | None = Field(
        default=None, description="Observaciones posturales (basculación pélvica, hombros…)."
    )
    overall_impression: str = Field(..., description="Resumen ejecutivo del estado físico.")

    @field_validator("estimated_body_fat_range")
    @classmethod
    def _validate_bf_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        """Garantiza low ≤ high y ambos en (0, 60)%."""
        lo, hi = v
        if not (0 < lo <= hi < 60):
            raise ValueError(f"estimated_body_fat_range inválido: {v}")
        return v


# ---------------------------------------------------------- Estimaciones


_SEX_BMR_OFFSET: dict[Literal["M", "F"], int] = {"M": 5, "F": -161}


class MetabolicEstimates(BaseModel):
    """Estimaciones metabólicas (Mifflin-St Jeor) y métricas derivadas."""

    bmr: float = Field(..., gt=0, description="Tasa metabólica basal (kcal/día).")
    tdee: float = Field(..., gt=0, description="Gasto diario total estimado (kcal/día).")
    activity_factor: float = Field(..., gt=0, description="Multiplicador aplicado al BMR.")
    bmi: float = Field(..., gt=0, description="Índice de masa corporal (referencial).")
    waist_hip_ratio: float | None = Field(default=None, gt=0)
    estimated_bf_formula: float | None = Field(
        default=None, ge=0, lt=60, description="% graso estimado por fórmula (Navy/JP)."
    )

    @classmethod
    def from_basic_data(
        cls,
        *,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: Literal["M", "F"],
        activity_factor: float,
        waist_cm: float | None = None,
        hip_cm: float | None = None,
        estimated_bf_formula: float | None = None,
    ) -> Self:
        """Calcula BMR (Mifflin-St Jeor), TDEE e IMC a partir de datos básicos.

        Mifflin-St Jeor: BMR = 10·kg + 6.25·cm − 5·edad + (5 si M, −161 si F).
        """
        bmr: float = 10 * weight_kg + 6.25 * height_cm - 5 * age + _SEX_BMR_OFFSET[sex]
        tdee: float = bmr * activity_factor
        height_m: float = height_cm / 100.0
        bmi: float = weight_kg / (height_m * height_m)
        whr: float | None = (waist_cm / hip_cm) if (waist_cm and hip_cm) else None
        return cls(
            bmr=round(bmr, 1),
            tdee=round(tdee, 1),
            activity_factor=activity_factor,
            bmi=round(bmi, 2),
            waist_hip_ratio=round(whr, 3) if whr is not None else None,
            estimated_bf_formula=estimated_bf_formula,
        )


# ---------------------------------------------------------- Recomendación


class PhaseRecommendation(BaseModel):
    """Recomendación de fase nutricional y volumen de entreno asociada."""

    recommended_phase: Literal[
        "cut", "minicut", "maintenance", "lean_bulk", "bulk", "recomposition"
    ]
    reasoning: str = Field(..., description="Justificación clínica de la fase elegida.")
    suggested_duration_weeks: int = Field(..., gt=0, le=52)
    suggested_calorie_target: int = Field(..., gt=0)
    suggested_macros: MacroDistribution


# ----------------------------------------------------- BodyAssessment


class BodyAssessment(BaseModel):
    """Evaluación corporal completa (puntual o periódica)."""

    id: str
    user_id: str
    date: date
    measurements: BodyMeasurements
    visual: VisualAssessment
    metabolic: MetabolicEstimates
    phase_recommendation: PhaseRecommendation
    photos_analyzed: list[str] = Field(default_factory=list)
    notes: str | None = None
