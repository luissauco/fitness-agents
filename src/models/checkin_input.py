"""Datos que el usuario aporta en el check-in bisemanal.

`CheckinInput` es el contrato de entrada al agente Progress. Se mantiene
flexible (training_logs sin schema estricto) para no penalizar la entrada
desde la app o un Excel del usuario.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.models.body_assessment import BodyMeasurements
from src.models.progress_log import SubjectiveFeedback


class CheckinInput(BaseModel):
    """Datos crudos de un check-in bisemanal."""

    weights: list[float] = Field(..., min_length=1, description="Pesos del periodo (kg).")
    measurements: BodyMeasurements
    photos: list[str] | None = Field(
        default=None,
        description="Paths a fotos nuevas (frente/espalda/perfiles), opcional.",
    )
    training_logs: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Lista de registros del entreno: "
            "[{exercise_id, sets: [{weight_kg, reps}], notes}]."
        ),
    )
    nutrition_adherence_self_estimate: float = Field(
        ..., ge=0.0, le=1.0, description="Adherencia auto-percibida 0–1."
    )
    cheat_meals_count: int = Field(..., ge=0)
    daily_steps_avg: int = Field(..., ge=0)
    subjective: SubjectiveFeedback
    user_notes: str | None = None
