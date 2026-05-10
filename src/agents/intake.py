"""Agente conversacional que recoge el cuestionario inicial del usuario.

`IntakeAgent` no es one-shot: mantiene una sesión stateful (`IntakeSession`) y
devuelve `IntakeTurn` por cada mensaje del usuario. Internamente apoya cada
turno en una llamada a Claude con structured output, decide la siguiente
pregunta y, cuando ya tiene todo, construye el `UserProfile` final.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import ClassVar, Final

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.knowledge.retriever import AgentType
from src.models.intake_session import IntakeSession, IntakeTurn
from src.models.questionnaire import (
    Question,
    Questionnaire,
    QuestionnaireResponse,
    QuestionType,
)
from src.models.user_profile import UserProfile

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Cuántos turnos del historial se inyectan al LLM en cada llamada.
_HISTORY_WINDOW: Final[int] = 8

# Tipo de pregunta que requiere imagen adjunta del usuario.
_IMAGE_TYPE: Final[QuestionType] = QuestionType.IMAGE


# ----------------------------------------------------- Output estructurado de la LLM


class _ExtractedAnswer(BaseModel):
    """Respuesta atómica que la LLM extrae del mensaje del usuario."""

    question_id: str = Field(..., description="Id de la pregunta del cuestionario.")
    value: str | int | float | list[str] | None = Field(
        default=None,
        description="Valor primario de la respuesta (None si la pregunta es de imagen).",
    )


class _IntakeLLMOutput(BaseModel):
    """Estructura que la LLM rellena en cada turno vía tool_use."""

    assistant_message: str = Field(..., description="Mensaje al usuario en español.")
    new_responses: list[_ExtractedAnswer] = Field(
        default_factory=list,
        description="Respuestas extraídas del último mensaje del usuario.",
    )
    next_question_id: str | None = Field(
        default=None,
        description="Id de la pregunta hacia la que apunta el siguiente turno.",
    )
    is_complete: bool = Field(default=False)


# -------------------------------------------------------------------- IntakeAgent


class IntakeAgent(BaseAgent):
    """Entrevistador inicial. No consulta RAG (agent_type=None)."""

    name: ClassVar[str] = "intake"
    agent_type: ClassVar[AgentType | None] = None

    @property
    def model(self) -> str:
        """Modelo de Claude usado por este agente (configurable vía settings)."""
        return self.settings.MODEL_SONNET

    # ------------------------------------------------------------ Ciclo de vida

    async def start_session(self, user_id: str) -> IntakeSession:
        """Crea una sesión nueva con el cuestionario default y bloque inicial."""
        questionnaire: Questionnaire = Questionnaire.get_default()
        first_block: str = next(iter(questionnaire.blocks))
        return IntakeSession(
            id=uuid.uuid4().hex[:12],
            user_id=user_id,
            started_at=datetime.now(),
            questionnaire=questionnaire,
            current_block=first_block,
        )

    async def build_profile(self, session: IntakeSession) -> UserProfile:
        """Construye el `UserProfile` a partir de las respuestas validadas.

        Lanza `ValueError` si quedan preguntas obligatorias sin responder.
        """
        missing: list[str] = session.questionnaire.missing_required(session.responses)
        if missing:
            raise ValueError(
                f"Cuestionario incompleto. Preguntas obligatorias pendientes: {missing}"
            )
        return UserProfile.from_questionnaire(session.responses, user_id=session.user_id)

    # ------------------------------------------------------------ Turno principal

    async def process_response(
        self,
        session: IntakeSession,
        user_message: str,
        attached_images: list[str] | None = None,
    ) -> IntakeTurn:
        """Procesa la respuesta del usuario y devuelve el siguiente turno."""
        # 1) Si el usuario adjunta imágenes, las imputamos a la pregunta IMAGE activa.
        if attached_images:
            self._absorb_images(session, attached_images)

        # 2) Determina la pregunta activa (siguiente obligatoria sin responder).
        active: Question | None = self._next_active_question(session)

        # 3) Llama al LLM con el contexto estructurado del estado.
        llm_out: _IntakeLLMOutput = await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=self._build_user_prompt(session, user_message, active),
            response_model=_IntakeLLMOutput,
            temperature=0.6,
        )

        # 4) Consolida respuestas extraídas y actualiza historial.
        if user_message:
            session.append_message("user", user_message)
        session.append_message("assistant", llm_out.assistant_message)
        for extracted in llm_out.new_responses:
            self._merge_extracted(session, extracted)

        # 5) Calcula estado posterior (completitud, próxima pregunta, awaiting_image).
        pending: list[str] = session.questionnaire.missing_required(session.responses)
        is_complete: bool = bool(llm_out.is_complete) and not pending
        if is_complete and session.completed_at is None:
            session.completed_at = datetime.now()

        next_qid: str | None = None if is_complete else llm_out.next_question_id
        next_q: Question | None = (
            session.questionnaire.find_question(next_qid) if next_qid else None
        )
        if next_q is not None:
            session.current_block = next_q.block
        awaiting: bool = next_q is not None and next_q.question_type == _IMAGE_TYPE
        # Memoriza la pregunta IMAGE pedida para el próximo turno con adjuntos.
        session.expected_image_question_id = next_q.id if awaiting else None

        return IntakeTurn(
            assistant_message=llm_out.assistant_message,
            is_complete=is_complete,
            next_question_id=next_qid,
            validated_responses=list(session.responses),
            pending_questions=pending,
            awaiting_image=awaiting,
        )

    # ------------------------------------------------------------- Helpers internos

    def _next_active_question(self, session: IntakeSession) -> Question | None:
        """Devuelve la siguiente pregunta obligatoria sin responder, o None."""
        answered: set[str] = session.answered_ids()
        for q in session.questionnaire.all_questions():
            if q.required and q.id not in answered:
                return q
        return None

    def _absorb_images(self, session: IntakeSession, image_paths: list[str]) -> None:
        """Asocia los paths recibidos a la pregunta IMAGE que el agente estaba pidiendo.

        Prioriza `expected_image_question_id` (lo fija el turno anterior cuando
        `awaiting_image=True`). Si no hay expectativa concreta, recurre a la
        primera pregunta IMAGE obligatoria sin responder, y como último recurso
        a la primera IMAGE sin responder (incluyendo opcionales).
        """
        target_id: str | None = self._pick_image_target(session)
        if target_id is None:
            _logger.warning(
                "intake.images_unmatched",
                extra={"session_id": session.id, "n_images": len(image_paths)},
            )
            return
        session.upsert_response(
            QuestionnaireResponse(question_id=target_id, image_paths=list(image_paths))
        )
        # La expectativa se consume tras absorber.
        if session.expected_image_question_id == target_id:
            session.expected_image_question_id = None

    def _pick_image_target(self, session: IntakeSession) -> str | None:
        """Resuelve a qué `question_id` IMAGE asignar las imágenes entrantes."""
        answered: set[str] = session.answered_ids()
        expected: str | None = session.expected_image_question_id
        if expected and expected not in answered:
            q: Question | None = session.questionnaire.find_question(expected)
            if q is not None and q.question_type == _IMAGE_TYPE:
                return expected

        # Fallbacks por orden canónico: primero obligatorias, luego cualquiera.
        for required_only in (True, False):
            for q in session.questionnaire.all_questions():
                if q.question_type != _IMAGE_TYPE or q.id in answered:
                    continue
                if required_only and not q.required:
                    continue
                return q.id
        return None

    def _merge_extracted(
        self,
        session: IntakeSession,
        extracted: _ExtractedAnswer,
    ) -> None:
        """Convierte una extracción de la LLM en `QuestionnaireResponse` y la guarda.

        Descarta silenciosamente extracciones referidas a preguntas inexistentes
        o a preguntas tipo IMAGE (esas las maneja `_absorb_images`).
        """
        question: Question | None = session.questionnaire.find_question(extracted.question_id)
        if question is None or question.question_type == _IMAGE_TYPE:
            return
        if extracted.value is None:
            return
        session.upsert_response(
            QuestionnaireResponse(question_id=extracted.question_id, value=extracted.value)
        )

    def _build_user_prompt(
        self,
        session: IntakeSession,
        user_message: str,
        active: Question | None,
    ) -> str:
        """Compone el bloque de contexto que se envía como user message al LLM."""
        answered: list[str] = sorted(session.answered_ids())
        pending: list[str] = session.questionnaire.missing_required(session.responses)

        lines: list[str] = [
            "## ESTADO DE LA SESIÓN",
            f"- Bloque actual: {session.current_block}",
            f"- Respuestas registradas: {len(session.responses)} (ids: {answered or '—'})",
            f"- Preguntas obligatorias pendientes: {pending or '—'}",
            "",
            "## PREGUNTA ACTIVA",
        ]
        if active is None:
            lines.append("(No hay pregunta activa: el cuestionario está completo.)")
        else:
            lines.append(self._format_question(active))

        history: list[dict[str, object]] = session.conversation_history[-_HISTORY_WINDOW:]
        if history:
            lines.append("")
            lines.append("## HISTORIAL RECIENTE")
            for turn in history:
                role: str = "Usuario" if turn.get("role") == "user" else "Tú (asistente)"
                lines.append(f"- {role}: {turn.get('content', '')}")

        lines.append("")
        lines.append("## MENSAJE ACTUAL DEL USUARIO")
        lines.append(user_message or "(sin mensaje: es el inicio de la conversación)")
        lines.append("")
        lines.append(
            "Decide tu próximo turno. Si el mensaje del usuario contiene "
            "información válida para alguna pregunta, inclúyela en `new_responses`. "
            "Si la entrada es ambigua, pide clarificación en `assistant_message` y "
            "deja `new_responses` vacío. Llama al tool `submit_response`."
        )
        return "\n".join(lines)

    @staticmethod
    def _format_question(q: Question) -> str:
        """Renderiza una `Question` como texto legible para el contexto del LLM."""
        parts: list[str] = [
            f"- id: {q.id}",
            f"- bloque: {q.block}",
            f"- tipo: {q.question_type.value}",
            f"- texto: {q.text}",
        ]
        if q.options:
            parts.append(f"- opciones válidas: {q.options}")
        if q.validation_hint:
            parts.append(f"- formato esperado: {q.validation_hint}")
        if not q.required:
            parts.append("- opcional: True")
        return "\n".join(parts)
