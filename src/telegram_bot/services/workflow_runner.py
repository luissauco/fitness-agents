"""Wrapper sobre el workflow LangGraph para uso desde el bot de Telegram.

Ofrece una API simple (WorkflowInput → WorkflowOutput) que abstrae al bot
de los detalles del grafo. El estado por usuario se persiste automáticamente
a través del checkpointer SQLite configurado en el workflow compilado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal

from langgraph.graph.state import CompiledStateGraph

from cli.commands.factory import Repositories, persist_artifacts
from src.graph.state import FitnessState, initial_state
from src.models.checkin_input import CheckinInput
from src.models.questionnaire import Question

_logger: Final[logging.Logger] = logging.getLogger(__name__)


# ----------------------------------------------------------------- DTOs


@dataclass
class WorkflowInput:
    """Input genérico para una invocación del workflow desde el bot."""

    user_id: str
    phase_hint: Literal["onboarding", "checkin"] | None = None
    user_message: str | None = None
    image_paths: list[Path] = field(default_factory=list)
    checkin_data: CheckinInput | None = None
    regenerate_plan: bool = False


@dataclass
class WorkflowOutput:
    """Resultado de una invocación, listo para traducir a mensajes de Telegram."""

    current_phase: str
    assistant_message: str | None
    current_question: Question | None
    needs_user_input: bool
    expecting_images: bool
    generated_files: list[Path]
    next_checkin_date: date | None
    warnings: list[str]
    errors: list[str]
    is_complete: bool


# ------------------------------------------------------------- Runner


class WorkflowRunner:
    """Wrapper sobre el grafo LangGraph que ofrece API simple para Telegram.

    El estado por usuario se persiste entre llamadas a través del checkpointer
    SQLite integrado en el workflow compilado (thread_id = user_id).
    """

    def __init__(self, workflow: CompiledStateGraph, repos: Repositories) -> None:
        self._workflow = workflow
        self._repos = repos

    async def invoke(self, wf_input: WorkflowInput) -> WorkflowOutput:
        """Ejecuta el workflow con el input del usuario y devuelve el output traducible."""
        config: dict[str, Any] = {"configurable": {"thread_id": wf_input.user_id}}

        # Estado previo para detectar archivos nuevos
        prev_snapshot = await self._workflow.aget_state(config)
        prev_files: set[str] = set((prev_snapshot.values or {}).get("generated_files") or [])

        # Construir el input del grafo
        graph_input = self._build_graph_input(wf_input, prev_snapshot.values)

        # Ejecutar el grafo
        final_state: FitnessState = await self._workflow.ainvoke(graph_input, config=config)

        # Persistir artefactos nuevos en SQLite
        persist_artifacts(final_state, self._repos)

        return self._to_output(final_state, prev_files)

    # ---------------------------------------------------------- Helpers privados

    def _build_graph_input(
        self,
        wf_input: WorkflowInput,
        current_values: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Construye el dict de input para ainvoke.

        Si no hay estado previo (usuario nuevo), parte del estado inicial.
        Si ya hay estado, solo envía el delta con la entrada del usuario.
        """
        is_new_user = not current_values

        if wf_input.regenerate_plan:
            # Usuario con perfil pero sin mesociclo: reconstruir estado desde BD
            # y saltar directamente a la fase de planificación.
            base = dict(initial_state(wf_input.user_id))
            profile = self._repos.user_profile.get(wf_input.user_id)
            assessment = self._repos.body_assessment.get_latest(wf_input.user_id)
            base["user_profile"] = profile
            base["body_assessment"] = assessment
            base["current_phase"] = "planning"
            base["pending_user_input"] = None
            base["pending_user_images"] = None
            return base

        if is_new_user:
            base: dict[str, Any] = dict(initial_state(wf_input.user_id))
        else:
            base = {}

        # Aplicar el input del usuario
        if wf_input.checkin_data is not None:
            base["pending_checkin_data"] = wf_input.checkin_data
            base["current_phase"] = "checkin"
            base["pending_user_input"] = None
            base["pending_user_images"] = None
        elif wf_input.image_paths:
            base["pending_user_images"] = [str(p) for p in wf_input.image_paths]
            base["pending_user_input"] = ""
        else:
            base["pending_user_input"] = wf_input.user_message or ""
            base["pending_user_images"] = None

        return base

    def _to_output(self, state: FitnessState, prev_files: set[str]) -> WorkflowOutput:
        """Traduce FitnessState al WorkflowOutput que consume el bot."""
        phase: str = state.get("current_phase") or "onboarding"
        pending_action: str | None = state.get("pending_action")

        # Mensaje del asistente — solo durante onboarding viene del historial de intake
        assistant_message: str | None = None
        session = state.get("intake_session")
        if session and session.conversation_history:
            last = session.conversation_history[-1]
            if last.get("role") == "assistant":
                assistant_message = str(last.get("content", ""))

        # Pregunta actual (para decidir el teclado inline)
        current_question: Question | None = self._resolve_current_question(state)

        expecting_images = pending_action == "awaiting_image"
        needs_user_input = phase == "onboarding" and not state.get("user_profile")

        # Solo archivos generados en ESTA invocación
        all_files: set[str] = set(state.get("generated_files") or [])
        new_files: list[Path] = [Path(f) for f in sorted(all_files - prev_files)]

        is_complete = phase in ("active", "completed")

        return WorkflowOutput(
            current_phase=phase,
            assistant_message=assistant_message,
            current_question=current_question,
            needs_user_input=needs_user_input,
            expecting_images=expecting_images,
            generated_files=new_files,
            next_checkin_date=state.get("next_checkin_date"),
            warnings=list(state.get("warnings") or []),
            errors=list(state.get("errors") or []),
            is_complete=is_complete,
        )

    @staticmethod
    def _resolve_current_question(state: FitnessState) -> Question | None:
        """Devuelve la Question activa del intake para determinar el tipo de teclado.

        Prioriza `expected_image_question_id` si está seteado. En otro caso,
        busca la primera pregunta requerida sin respuesta en el cuestionario.
        """
        session = state.get("intake_session")
        if session is None:
            return None

        # Si el agente está esperando una imagen, esa es la pregunta activa
        if session.expected_image_question_id:
            q = session.questionnaire.find_question(session.expected_image_question_id)
            if q is not None:
                return q

        # Buscar la primera pregunta obligatoria sin responder
        answered: set[str] = session.answered_ids()
        for q in session.questionnaire.all_questions():
            if q.required and q.id not in answered:
                return q

        return None
