"""Mesociclos de entrenamiento y su estructura jerárquica.

Mesocycle → Microcycle → TrainingDay → ProgrammedExercise → SetScheme + ExerciseLog.

Modelo central del sistema: lo consumen el agente entrenador para programar
y el generador de Excel para producir el archivo final.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Técnicas avanzadas reconocidas en `SetScheme.technique`.
SetTechnique = Literal["straight", "top_back_off", "rest_pause", "drop_set", "superset", "myo_reps"]

# Fases de mesociclo y tipos de split.
MesocyclePhase = Literal[
    "hypertrophy", "strength", "cut", "minicut", "lean_bulk", "maintenance", "deload"
]
SplitType = Literal[
    "full_body", "upper_lower", "push_pull_legs", "push_pull", "bro_split", "torso_legs"
]


class SetScheme(BaseModel):
    """Esquema de series para un ejercicio en un día concreto."""

    total_sets: int = Field(..., ge=1, le=20)
    rep_range: tuple[int, int] = Field(..., description="Rango (min, max) de repeticiones.")
    rir: int = Field(..., ge=0, le=5, description="Repeticiones en reserva objetivo.")
    is_to_failure: bool = False
    technique: SetTechnique | None = None
    top_set_count: int | None = Field(default=None, ge=1)
    backoff_set_count: int | None = Field(default=None, ge=1)
    backoff_rir: int | None = Field(default=None, ge=0, le=5)
    superset_with: str | None = Field(default=None, description="ID del ejercicio en superserie.")
    rest_seconds: int = Field(default=120, ge=0, le=600)
    description: str = Field(
        ..., description="Texto legible (ej: 'top set: 1x?(1) / back-off: 2x?(1)')."
    )

    @field_validator("rep_range")
    @classmethod
    def _validate_rep_range(cls, v: tuple[int, int]) -> tuple[int, int]:
        """Garantiza min ≤ max y ambos > 0."""
        lo, hi = v
        if lo <= 0 or lo > hi:
            raise ValueError(f"rep_range inválido: {v}")
        return v

    @model_validator(mode="after")
    def _validate_technique(self) -> SetScheme:
        """Coherencia entre `technique` y los campos opcionales asociados."""
        if self.technique == "top_back_off":
            if self.top_set_count is None or self.backoff_set_count is None:
                raise ValueError(
                    "technique='top_back_off' requiere top_set_count y backoff_set_count."
                )
            if self.top_set_count + self.backoff_set_count != self.total_sets:
                raise ValueError("top_set_count + backoff_set_count debe igualar total_sets.")
        if self.technique == "superset" and not self.superset_with:
            raise ValueError("technique='superset' requiere superset_with.")
        return self


class ExerciseLog(BaseModel):
    """Registro real de un ejercicio en un microciclo concreto.

    `sets` es una lista de dicts con la forma `{"weight_kg": float, "reps": int}`.
    Se mantiene flexible (no Pydantic estricto) para no penalizar la entrada
    desde la app o un Excel.
    """

    sets: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None
    perceived_difficulty: Literal["easy", "moderate", "hard", "maximal"] | None = None


class ProgrammedExercise(BaseModel):
    """Un ejercicio dentro de un día de entrenamiento, con su esquema y logs."""

    order: int = Field(..., ge=1, description="Posición del ejercicio en el día.")
    exercise_id: str = Field(..., description="Referencia al catálogo `ExerciseDatabase`.")
    exercise_name: str = Field(
        ..., description="Nombre completo con indicaciones técnicas (ej: 'Press inclinado 30°')."
    )
    set_scheme: SetScheme
    logs: dict[int, ExerciseLog] = Field(
        default_factory=dict, description="microciclo_number → registro real."
    )
    progression_notes: str | None = None


class TrainingDay(BaseModel):
    """Un día del microciclo. Puede ser de descanso (sin ejercicios)."""

    day_number: int = Field(..., ge=1, le=10, description="Día dentro del microciclo (1-N).")
    day_label: str = Field(..., description="Etiqueta legible (ej: 'Día 1 - Torso A').")
    is_rest_day: bool = False
    exercises: list[ProgrammedExercise] = Field(default_factory=list)
    target_steps: int = Field(default=10000, ge=0, description="Pasos mínimos del día.")
    cardio_notes: str | None = None

    @model_validator(mode="after")
    def _check_rest_consistency(self) -> TrainingDay:
        """Un día de descanso no puede llevar ejercicios programados."""
        if self.is_rest_day and self.exercises:
            raise ValueError("Un día marcado como descanso no debe tener ejercicios.")
        return self


class Microcycle(BaseModel):
    """Bloque semanal (o de 10 días) dentro del mesociclo."""

    number: int = Field(..., ge=1)
    duration_days: int = Field(default=7, ge=1, le=14)
    is_deload: bool = False
    volume_modifier: float = Field(
        default=1.0, gt=0, le=2.0, description="Multiplicador del volumen base."
    )
    intensity_modifier: float = Field(
        default=1.0, gt=0, le=1.5, description="Multiplicador de la intensidad base."
    )
    training_days: list[TrainingDay]
    notes: str | None = None

    @model_validator(mode="after")
    def _check_days_count(self) -> Microcycle:
        """Número de training_days no debe exceder duration_days."""
        if len(self.training_days) > self.duration_days:
            raise ValueError(
                f"training_days ({len(self.training_days)}) > duration_days ({self.duration_days})."
            )
        return self


class WeeklySchedule(BaseModel):
    """Esquema semanal de referencia: tipo de día y pasos mínimos.

    `days` es una lista de dicts con la forma:
        {"day": 1, "type": "pesas", "steps": 10500}
        {"day": 3, "type": "descanso", "steps": 12500}
    """

    days: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class Mesocycle(BaseModel):
    """Mesociclo completo de entrenamiento."""

    id: str
    user_id: str
    name: str = Field(..., description="Nombre legible (ej: 'Hipertrofia Upper/Lower 4 micros').")
    start_date: date
    end_date: date | None = Field(
        default=None,
        description="Calculada a partir de start_date + suma de microcycle.duration_days.",
    )
    phase: MesocyclePhase
    split_type: SplitType
    training_days_per_week: int = Field(..., ge=1, le=7)
    microcycles: list[Microcycle] = Field(..., min_length=1)
    weekly_schedule: WeeklySchedule
    progression_strategy: str = Field(
        ..., description="Cómo se progresa entre microciclos (ej: '+1 RIR/-1 set deload')."
    )
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def _backfill_end_date(self) -> Mesocycle:
        """Calcula `end_date` si no se proporcionó."""
        if self.end_date is None:
            total_days: int = sum(m.duration_days for m in self.microcycles)
            object.__setattr__(self, "end_date", self.start_date + timedelta(days=total_days - 1))
        return self

    @property
    def total_weeks(self) -> int:
        """Total de semanas del mesociclo (redondeo al alza si hay micros de 10 días)."""
        total_days: int = sum(m.duration_days for m in self.microcycles)
        return math.ceil(total_days / 7)

    @property
    def current_microcycle(self) -> Microcycle | None:
        """Microciclo activo en la fecha de hoy. None si aún no empezó o ya terminó."""
        today: date = date.today()
        if today < self.start_date:
            return None
        days_in: int = (today - self.start_date).days
        cumulative: int = 0
        for m in self.microcycles:
            if days_in < cumulative + m.duration_days:
                return m
            cumulative += m.duration_days
        return None
