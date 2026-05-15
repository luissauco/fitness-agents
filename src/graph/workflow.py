"""Orquestador LangGraph del sistema fitness-agents.

Cada nodo encapsula la llamada a un agente y devuelve únicamente las claves del
`FitnessState` que toca; LangGraph hace merge automático.

El intake es conversacional: cada `ainvoke()` procesa **un turno** y, si la
sesión sigue abierta, el grafo termina hasta la siguiente entrada del usuario
(la CLI / bot orquesta el bucle externo).

Punto de entrada condicional según `current_phase`:
- `onboarding` → `intake`
- `assessment` → `assessment`
- `planning` → `training`
- `checkin` → `progress`
- otros → `END` (no hay nada que hacer en este turno)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.assessment import AssessmentAgent
from src.agents.intake import IntakeAgent
from src.agents.nutrition import NutritionAgent
from src.agents.progress import ProgressAgent
from src.agents.training import TrainingAgent
from src.generators.pdf_nutrition import NutritionPDFGenerator
from src.generators.pdf_progress import ProgressPDFGenerator
from src.generators.xlsx_mesocycle import MesocycleExcelGenerator
from src.graph.state import FitnessState
from src.models.body_assessment import BodyMeasurements

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Días entre check-ins bisemanales.
_CHECKIN_PERIOD_DAYS: Final[int] = 14


# ---------------------------------------------------- Bundle de dependencias


@dataclass
class AgentBundle:
    """Conjunto de agentes inyectados a los nodos del grafo."""

    intake: IntakeAgent
    assessment: AssessmentAgent
    training: TrainingAgent
    nutrition: NutritionAgent
    progress: ProgressAgent


# ----------------------------------------------------------------- Helpers


def _append_error(state: FitnessState, message: str) -> list[str]:
    """Devuelve la lista de errores con `message` añadido (no muta el estado)."""
    existing: list[str] = list(state.get("errors") or [])
    existing.append(message)
    return existing


def _with_generated_file(state: FitnessState, path: object) -> list[str]:
    """Devuelve `generated_files` con el path añadido (no muta el estado)."""
    files: list[str] = list(state.get("generated_files") or [])
    files.append(str(path))
    return files


# -------------------------------------------------------------------- Nodos


def _make_intake_node(bundle: AgentBundle):
    """Procesa un turno de cuestionario."""

    async def intake_node(state: FitnessState) -> dict[str, Any]:
        session = state.get("intake_session")
        user_input: str = state.get("pending_user_input") or ""
        images: list[str] | None = state.get("pending_user_images")

        if session is None:
            session = await bundle.intake.start_session(state["user_id"])

        try:
            turn = await bundle.intake.process_response(
                session=session,
                user_message=user_input,
                attached_images=images,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.intake_node.failed")
            return {"errors": _append_error(state, f"intake: {exc}")}

        update: dict[str, Any] = {
            "intake_session": session,
            "messages": [{"role": "assistant", "content": turn.assistant_message}],
            "pending_user_input": None,
            "pending_user_images": None,
            "pending_action": "awaiting_image" if turn.awaiting_image else "awaiting_text",
        }

        if turn.is_complete:
            try:
                profile = await bundle.intake.build_profile(session)
            except Exception as exc:  # noqa: BLE001
                _logger.exception("workflow.intake.build_profile_failed")
                update["errors"] = _append_error(state, f"build_profile: {exc}")
                return update
            update["user_profile"] = profile
            update["current_phase"] = "assessment"
            update["pending_action"] = None

        return update

    return intake_node


def _make_assessment_node(bundle: AgentBundle):
    """Genera la evaluación corporal."""

    async def assessment_node(state: FitnessState) -> dict[str, Any]:
        profile = state.get("user_profile")
        if profile is None:
            return {"errors": _append_error(state, "assessment: falta user_profile")}

        # Medidas mínimas a partir del peso del cuestionario; el resto es opcional.
        measurements = BodyMeasurements(weight_kg=profile.personal.weight_kg)

        try:
            assessment = await bundle.assessment.run(profile=profile, measurements=measurements)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.assessment_node.failed")
            return {"errors": _append_error(state, f"assessment: {exc}")}

        return {
            "body_assessment": assessment,
            "current_phase": "planning",
        }

    return assessment_node


def _make_training_node(bundle: AgentBundle):
    """Genera (o regenera) el mesociclo activo."""

    async def training_node(state: FitnessState) -> dict[str, Any]:
        profile = state.get("user_profile")
        assessment = state.get("body_assessment")
        if profile is None or assessment is None:
            return {
                "errors": _append_error(state, "training: faltan user_profile o body_assessment")
            }

        previous = state.get("current_mesocycle")
        try:
            mesocycle = await bundle.training.run(
                profile=profile,
                assessment=assessment,
                previous_mesocycle=previous,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.training_node.failed")
            return {"errors": _append_error(state, f"training: {exc}")}

        update: dict[str, Any] = {
            "current_mesocycle": mesocycle,
            "current_microcycle_index": 0,
        }
        try:
            path = MesocycleExcelGenerator().generate(mesocycle, profile.personal.name)
            update["generated_files"] = _with_generated_file(state, path)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.training_node.excel_failed")
            update["warnings"] = [
                *(state.get("warnings") or []),
                f"excel_mesociclo: {exc}",
            ]
        return update

    return training_node


def _make_nutrition_node(bundle: AgentBundle):
    """Genera (o regenera) el plan nutricional asociado al mesociclo activo."""

    async def nutrition_node(state: FitnessState) -> dict[str, Any]:
        profile = state.get("user_profile")
        assessment = state.get("body_assessment")
        mesocycle = state.get("current_mesocycle")
        if profile is None or assessment is None or mesocycle is None:
            return {
                "errors": _append_error(state, "nutrition: faltan profile/assessment/mesocycle")
            }

        previous_plan = state.get("current_nutrition_plan")
        try:
            plan = await bundle.nutrition.run(
                profile=profile,
                assessment=assessment,
                mesocycle=mesocycle,
                previous_plan=previous_plan,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.nutrition_node.failed")
            return {"errors": _append_error(state, f"nutrition: {exc}")}

        update: dict[str, Any] = {"current_nutrition_plan": plan}
        try:
            path = NutritionPDFGenerator().generate(plan, profile.personal.name)
            update["generated_files"] = _with_generated_file(state, path)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.nutrition_node.pdf_failed")
            update["warnings"] = [
                *(state.get("warnings") or []),
                f"pdf_nutricional: {exc}",
            ]
        return update

    return nutrition_node


def _make_progress_node(bundle: AgentBundle):
    """Procesa un check-in bisemanal y produce un `ProgressLog`."""

    async def progress_node(state: FitnessState) -> dict[str, Any]:
        profile = state.get("user_profile")
        mesocycle = state.get("current_mesocycle")
        plan = state.get("current_nutrition_plan")
        checkin = state.get("pending_checkin_data")
        if profile is None or mesocycle is None or plan is None or checkin is None:
            return {
                "errors": _append_error(state, "progress: faltan profile/mesocycle/plan/checkin")
            }

        previous_logs: list = list(state.get("progress_logs") or [])
        try:
            log = await bundle.progress.run(
                profile=profile,
                current_mesocycle=mesocycle,
                current_plan=plan,
                checkin_data=checkin,
                previous_logs=previous_logs,
                microcycle_completed=state.get("current_microcycle_index", 0) + 1,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.progress_node.failed")
            return {"errors": _append_error(state, f"progress: {exc}")}

        update: dict[str, Any] = {
            "progress_logs": [*previous_logs, log],
            "last_checkin_date": date.today(),
            "pending_checkin_data": None,
        }
        try:
            path = ProgressPDFGenerator().generate(
                log, profile.personal.name, previous_logs=previous_logs
            )
            update["generated_files"] = _with_generated_file(state, path)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("workflow.progress_node.pdf_failed")
            update["warnings"] = [
                *(state.get("warnings") or []),
                f"pdf_progreso: {exc}",
            ]
        return update

    return progress_node


async def schedule_checkin_node(state: FitnessState) -> dict[str, Any]:
    """Programa el siguiente check-in y deja al usuario en fase activa."""
    today: date = date.today()
    return {
        "next_checkin_date": today + timedelta(days=_CHECKIN_PERIOD_DAYS),
        "current_phase": "active",
    }


async def advance_microcycle_node(state: FitnessState) -> dict[str, Any]:
    """Avanza al siguiente microciclo y reprograma el próximo check-in."""
    mesocycle = state.get("current_mesocycle")
    current_idx: int = int(state.get("current_microcycle_index", 0))
    next_idx: int = current_idx + 1
    today: date = date.today()
    update: dict[str, Any] = {
        "current_microcycle_index": next_idx,
        "next_checkin_date": today + timedelta(days=_CHECKIN_PERIOD_DAYS),
        "current_phase": "active",
    }
    if mesocycle is not None and next_idx >= len(mesocycle.microcycles):
        update["current_phase"] = "completed"
    return update


# ---------------------------------------------------------------- Routers


def route_entry(state: FitnessState) -> str:
    """Selección de nodo inicial según `current_phase` y datos disponibles."""
    phase = state.get("current_phase", "onboarding")
    if phase == "onboarding":
        return "intake"
    if phase == "assessment":
        return "assessment"
    if phase == "planning":
        return "training"
    if phase == "checkin" and state.get("pending_checkin_data") is not None:
        return "progress"
    return END


def route_after_intake(state: FitnessState) -> str:
    """Tras un turno de intake: si aún no hay perfil completo, esperamos al usuario."""
    if state.get("user_profile") is None:
        return END
    return "assessment"


def route_after_assessment(state: FitnessState) -> str:
    """Si la evaluación falló, paramos; si hubo éxito, generamos plan."""
    if state.get("body_assessment") is None:
        return END
    return "training"


def route_after_planning(state: FitnessState) -> str:
    """Tras nutrición: si hay plan completo, programamos check-in."""
    if state.get("current_mesocycle") and state.get("current_nutrition_plan"):
        return "schedule_checkin"
    return END


def route_after_progress(state: FitnessState) -> str:
    """Despacha según la decisión del último `ProgressLog`."""
    logs = state.get("progress_logs") or []
    if not logs:
        return END
    decision = logs[-1].decision.action
    if decision == "new_mesocycle":
        return "training"
    if decision in ("adjust_calories", "adjust_macros"):
        return "nutrition"
    if decision == "adjust_volume":
        return "training"
    # `continue` o `early_deload` (esta última ya está prevista en el mesociclo)
    return "advance_microcycle"


# --------------------------------------------------------- Construcción del grafo


def build_workflow(
    bundle: AgentBundle,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Construye y compila el `StateGraph` del flujo completo."""
    workflow: StateGraph = StateGraph(FitnessState)

    workflow.add_node("intake", _make_intake_node(bundle))
    workflow.add_node("assessment", _make_assessment_node(bundle))
    workflow.add_node("training", _make_training_node(bundle))
    workflow.add_node("nutrition", _make_nutrition_node(bundle))
    workflow.add_node("progress", _make_progress_node(bundle))
    workflow.add_node("schedule_checkin", schedule_checkin_node)
    workflow.add_node("advance_microcycle", advance_microcycle_node)

    workflow.set_conditional_entry_point(
        route_entry,
        {
            "intake": "intake",
            "assessment": "assessment",
            "training": "training",
            "progress": "progress",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "intake", route_after_intake, {"assessment": "assessment", END: END}
    )
    workflow.add_conditional_edges(
        "assessment", route_after_assessment, {"training": "training", END: END}
    )
    workflow.add_edge("training", "nutrition")
    workflow.add_conditional_edges(
        "nutrition",
        route_after_planning,
        {"schedule_checkin": "schedule_checkin", END: END},
    )
    workflow.add_edge("schedule_checkin", END)

    workflow.add_conditional_edges(
        "progress",
        route_after_progress,
        {
            "training": "training",
            "nutrition": "nutrition",
            "advance_microcycle": "advance_microcycle",
            END: END,
        },
    )
    workflow.add_edge("advance_microcycle", END)

    return workflow.compile(checkpointer=checkpointer)
