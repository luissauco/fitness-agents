"""Estado global del workflow LangGraph del sistema fitness-agents.

`FitnessState` es el `TypedDict` que comparten todos los nodos del grafo.
LangGraph hace merge automático de las claves devueltas por cada nodo, así que
los nodos solo retornan las claves que tocan.

Notas:
- Los modelos Pydantic se almacenan tal cual; el `JsonPlusSerializer` del
  checkpointer los serializa con `model_dump()` y los reconstruye al hidratar.
- `messages` usa `add_messages` para acumular conversación entre turnos.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import add_messages

from src.models.body_assessment import BodyAssessment
from src.models.checkin_input import CheckinInput
from src.models.intake_session import IntakeSession
from src.models.mesocycle import Mesocycle
from src.models.nutrition_plan import NutritionPlan
from src.models.progress_log import ProgressLog
from src.models.user_profile import UserProfile

# Fases del flujo del usuario, en orden cronológico habitual.
PhaseLiteral = Literal[
    "onboarding",  # cuestionario en curso
    "assessment",  # evaluando con fotos/medidas
    "planning",  # generando mesociclo y dieta
    "active",  # usuario en período activo de entrenamiento
    "checkin",  # procesando check-in bisemanal
    "completed",  # mesociclo terminado, esperando nuevo
]


class FitnessState(TypedDict, total=False):
    """Estado global del flujo del sistema.

    `total=False` permite que los nodos retornen dicts parciales sin que el
    type checker se queje; LangGraph hace merge sobre las claves presentes.
    """

    # Identificación
    user_id: str
    session_id: str
    current_phase: PhaseLiteral

    # Perfil del usuario (se construye en intake)
    user_profile: UserProfile | None
    intake_session: IntakeSession | None  # solo durante onboarding

    # Evaluación (se construye en assessment)
    body_assessment: BodyAssessment | None

    # Plan activo
    current_mesocycle: Mesocycle | None
    current_nutrition_plan: NutritionPlan | None
    current_microcycle_index: int  # 0-indexed sobre `current_mesocycle.microcycles`

    # Progreso
    progress_logs: list[ProgressLog]
    last_checkin_date: date | None
    next_checkin_date: date | None
    pending_checkin_data: CheckinInput | None

    # Conversación (intake u otros agentes conversacionales)
    messages: Annotated[list[dict[str, Any]], add_messages]
    pending_user_input: str | None  # texto del usuario aún sin procesar
    pending_user_images: list[str] | None  # imágenes adjuntas en el último turno
    pending_action: str | None  # próxima acción que la UI espera ejecutar

    # Outputs generados (paths a archivos)
    generated_files: list[str]

    # Errores y warnings acumulados
    errors: list[str]
    warnings: list[str]


def initial_state(user_id: str) -> FitnessState:
    """Estado inicial para un usuario nuevo (entra en `onboarding`)."""
    return FitnessState(
        user_id=user_id,
        session_id=uuid.uuid4().hex,
        current_phase="onboarding",
        user_profile=None,
        intake_session=None,
        body_assessment=None,
        current_mesocycle=None,
        current_nutrition_plan=None,
        current_microcycle_index=0,
        progress_logs=[],
        last_checkin_date=None,
        next_checkin_date=None,
        pending_checkin_data=None,
        messages=[],
        pending_user_input=None,
        pending_user_images=None,
        pending_action=None,
        generated_files=[],
        errors=[],
        warnings=[],
    )
