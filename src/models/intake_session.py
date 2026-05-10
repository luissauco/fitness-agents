"""Estado y output del agente Intake.

`IntakeSession` mantiene la conversación stateful con el usuario durante el
onboarding. `IntakeTurn` es el resultado de cada interacción y lo consume la
capa de UI (CLI hoy, bot/web mañana) para mostrar el siguiente mensaje y saber
qué entrada espera (texto vs imagen).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.questionnaire import Questionnaire, QuestionnaireResponse


class IntakeTurn(BaseModel):
    """Un turno de la conversación de intake (la respuesta del agente al usuario)."""

    assistant_message: str = Field(..., description="Mensaje del agente al usuario.")
    is_complete: bool = Field(
        default=False,
        description="True si todas las preguntas obligatorias están respondidas.",
    )
    next_question_id: str | None = Field(
        default=None,
        description="Id de la pregunta hacia la que apunta el siguiente turno.",
    )
    validated_responses: list[QuestionnaireResponse] = Field(
        default_factory=list,
        description="Snapshot de respuestas válidas acumuladas en la sesión.",
    )
    pending_questions: list[str] = Field(
        default_factory=list,
        description="Ids de preguntas obligatorias aún sin responder.",
    )
    awaiting_image: bool = Field(
        default=False,
        description="True si el siguiente turno espera adjuntar imágenes.",
    )


class IntakeSession(BaseModel):
    """Estado completo de una sesión de cuestionario."""

    id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None = None
    questionnaire: Questionnaire
    responses: list[QuestionnaireResponse] = Field(default_factory=list)
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de mensajes [{role: user|assistant, content: str}].",
    )
    current_block: str = Field(..., description="Bloque del cuestionario en el que está el agente.")
    expected_image_question_id: str | None = Field(
        default=None,
        description=(
            "Id de la pregunta IMAGE que el agente está pidiendo activamente. "
            "Se setea cuando el último turno marcó `awaiting_image=True` y se "
            "consume cuando llegan adjuntos en el siguiente turno."
        ),
    )

    # ----------------------------------------------------------------- Utilidades

    def answered_ids(self) -> set[str]:
        """Conjunto de ids de pregunta con respuesta no vacía."""
        return {r.question_id for r in self.responses if r.value is not None or r.image_paths}

    def append_message(self, role: str, content: str) -> None:
        """Añade un mensaje al historial de conversación."""
        self.conversation_history.append({"role": role, "content": content})

    def upsert_response(self, response: QuestionnaireResponse) -> None:
        """Inserta o reemplaza la respuesta a `question_id` (última respuesta gana)."""
        for i, existing in enumerate(self.responses):
            if existing.question_id == response.question_id:
                self.responses[i] = response
                return
        self.responses.append(response)
