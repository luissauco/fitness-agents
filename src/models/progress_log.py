"""Registro bisemanal de progreso del usuario.

Captura peso, medidas, progreso de entreno, adherencia nutricional, sensaciones
subjetivas, comparativa visual y la decisión tomada por el agente para el
siguiente periodo.
"""

from __future__ import annotations

from datetime import date, datetime
from statistics import mean
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from src.models.body_assessment import BodyMeasurements

# Umbral de variación de peso para considerar la tendencia "estable" (kg).
_WEIGHT_TREND_THRESHOLD: float = 0.2


class WeightLog(BaseModel):
    """Registro de peso del periodo: lista de mediciones y tendencia agregada."""

    weights: list[float] = Field(..., min_length=1, description="Pesos individuales (kg).")
    average: float = Field(..., gt=0, description="Media de las mediciones del periodo.")
    trend: Literal["losing", "stable", "gaining"]
    change_from_last: float | None = Field(
        default=None,
        description="Variación de la media frente al último registro (kg, signo).",
    )

    @classmethod
    def from_weights(cls, weights: list[float], *, last_average: float | None = None) -> Self:
        """Calcula `average`, `trend` y `change_from_last` a partir de la lista."""
        if not weights:
            raise ValueError("`weights` no puede estar vacía.")
        avg: float = round(mean(weights), 2)
        change: float | None = round(avg - last_average, 2) if last_average is not None else None
        trend: Literal["losing", "stable", "gaining"]
        if change is None or abs(change) <= _WEIGHT_TREND_THRESHOLD:
            trend = "stable"
        elif change < 0:
            trend = "losing"
        else:
            trend = "gaining"
        return cls(weights=weights, average=avg, trend=trend, change_from_last=change)


class TrainingProgress(BaseModel):
    """Progreso de entrenamiento agregado durante el periodo."""

    exercises_tracked: int = Field(..., ge=0)
    exercises_progressed: int = Field(..., ge=0)
    exercises_stagnated: int = Field(..., ge=0)
    exercises_regressed: int = Field(..., ge=0)
    volume_adherence_pct: float = Field(..., ge=0, le=100)
    notable_prs: list[str] = Field(default_factory=list)
    problem_exercises: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_counts(self) -> TrainingProgress:
        """progressed + stagnated + regressed no debe exceder tracked."""
        total: int = self.exercises_progressed + self.exercises_stagnated + self.exercises_regressed
        if total > self.exercises_tracked:
            raise ValueError(
                f"Suma de progresados/estancados/regresados ({total}) "
                f"> ejercicios trackeados ({self.exercises_tracked})."
            )
        return self


class SubjectiveFeedback(BaseModel):
    """Sensaciones subjetivas del usuario durante el periodo (escala 1-10)."""

    energy_level: int = Field(..., ge=1, le=10)
    sleep_quality: int = Field(..., ge=1, le=10)
    hunger_level: int = Field(..., ge=1, le=10, description="10 = mucha hambre.")
    motivation: int = Field(..., ge=1, le=10)
    stress_level: int = Field(..., ge=1, le=10)
    soreness: int = Field(..., ge=1, le=10, description="DOMS percibidas.")
    mood: int = Field(..., ge=1, le=10)
    pain_or_discomfort: str | None = None
    additional_notes: str | None = None


class NutritionAdherence(BaseModel):
    """Adherencia al plan nutricional durante el periodo."""

    adherence_pct: float = Field(..., ge=0, le=100)
    cheat_meals_count: int = Field(..., ge=0)
    missed_meals_avg: float = Field(..., ge=0, description="Comidas saltadas/día (media).")
    supplement_adherence: bool
    water_intake_liters: float = Field(..., ge=0, description="Litros/día (media).")
    notes: str | None = None


class PhotoComparison(BaseModel):
    """Comparativa visual entre fotos actuales y anteriores."""

    current_photos: list[str] = Field(..., min_length=1)
    previous_photos: list[str] = Field(default_factory=list)
    visual_changes: str = Field(..., description="Resumen de cambios observados.")
    areas_improved: list[str] = Field(default_factory=list)
    areas_unchanged: list[str] = Field(default_factory=list)


# Acciones que el agente puede decidir a partir del análisis de progreso.
ProgressAction = Literal[
    "continue",
    "adjust_calories",
    "adjust_macros",
    "adjust_volume",
    "early_deload",
    "change_phase",
    "new_mesocycle",
]


class ProgressDecision(BaseModel):
    """Decisión tomada tras el análisis del periodo, con detalle del ajuste."""

    action: ProgressAction
    reasoning: str = Field(..., description="Justificación de la decisión.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Detalles específicos del ajuste, ej: "
            "{'calorie_change': -200, 'new_target': 2100} para `adjust_calories`."
        ),
    )


class ProgressLog(BaseModel):
    """Registro completo del check-in bisemanal."""

    id: str
    user_id: str
    mesocycle_id: str
    microcycle_number: int = Field(..., ge=1, description="Microciclo recién terminado.")
    date: date
    period_start: date
    period_end: date
    weight: WeightLog
    measurements: BodyMeasurements
    training: TrainingProgress
    nutrition: NutritionAdherence
    subjective: SubjectiveFeedback
    photos: PhotoComparison | None = None
    daily_steps_avg: int = Field(..., ge=0)
    decision: ProgressDecision
    report_summary: str = Field(..., description="Resumen ejecutivo del periodo.")
    created_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def _check_period(self) -> ProgressLog:
        """`period_start` debe ser anterior o igual a `period_end`."""
        if self.period_start > self.period_end:
            raise ValueError(
                f"period_start ({self.period_start}) > period_end ({self.period_end})."
            )
        return self
