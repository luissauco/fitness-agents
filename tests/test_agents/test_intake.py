"""Tests del `IntakeAgent`.

Solo se mockea `ClaudeClient.generate_structured`; el `KnowledgeRetriever` se
instancia real (apuntando a la chroma de `tmp_path`) y `FakeEmbeddingManager`
para no descargar modelos. Como Intake declara `agent_type=None`, en realidad
nunca se llega a consultar el vector store.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.claude_client import ClaudeClient
from src.agents.intake import IntakeAgent, _ExtractedAnswer, _IntakeLLMOutput
from src.config.settings import Settings
from src.knowledge.retriever import KnowledgeRetriever
from src.models.intake_session import IntakeSession, IntakeTurn
from tests.helpers import FakeEmbeddingManager


@pytest.fixture
def intake_agent(settings: Settings, fake_embeddings: FakeEmbeddingManager) -> IntakeAgent:
    """Construye un `IntakeAgent` con `ClaudeClient` real (sin mockear todavía)."""
    retriever = KnowledgeRetriever(settings=settings, embedding_manager=fake_embeddings)
    claude = ClaudeClient(settings)
    return IntakeAgent(claude_client=claude, retriever=retriever, settings=settings)


def _patch_llm(agent: IntakeAgent, *outputs: _IntakeLLMOutput) -> AsyncMock:
    """Reemplaza `generate_structured` por un AsyncMock con respuestas en orden."""
    mock = AsyncMock(side_effect=list(outputs) if len(outputs) > 1 else None)
    if len(outputs) == 1:
        mock.return_value = outputs[0]
    agent.claude.generate_structured = mock  # type: ignore[method-assign]
    return mock


# ---------------------------------------------------------------- start_session


@pytest.mark.asyncio
async def test_start_session_initializes_first_block(intake_agent: IntakeAgent) -> None:
    """Sesión recién creada apunta al primer bloque (`datos_personales`)."""
    session: IntakeSession = await intake_agent.start_session(user_id="user-1")

    assert session.user_id == "user-1"
    assert session.current_block == "datos_personales"
    assert session.responses == []
    assert session.completed_at is None
    assert len(session.questionnaire.all_questions()) > 0


# --------------------------------------------------------------- process_response


@pytest.mark.asyncio
async def test_process_response_extracts_and_advances(intake_agent: IntakeAgent) -> None:
    """Respuesta válida → la respuesta se guarda y current_block avanza si toca."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    _patch_llm(
        intake_agent,
        _IntakeLLMOutput(
            assistant_message="¡Genial, Luis! ¿Cuántos años tienes?",
            new_responses=[_ExtractedAnswer(question_id="nombre", value="Luis")],
            next_question_id="edad",
            is_complete=False,
        ),
    )

    turn: IntakeTurn = await intake_agent.process_response(session, "Me llamo Luis")

    assert turn.is_complete is False
    assert turn.next_question_id == "edad"
    assert turn.awaiting_image is False
    # Se guardó la respuesta extraída.
    saved = next(r for r in session.responses if r.question_id == "nombre")
    assert saved.value == "Luis"
    # El historial registra ambos lados de la conversación.
    assert {m["role"] for m in session.conversation_history} == {"user", "assistant"}


@pytest.mark.asyncio
async def test_process_response_keeps_pending_when_ambiguous(
    intake_agent: IntakeAgent,
) -> None:
    """Si la LLM devuelve `new_responses=[]`, la pregunta sigue pendiente."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    _patch_llm(
        intake_agent,
        _IntakeLLMOutput(
            assistant_message="Necesito tu nombre completo, ¿me lo confirmas?",
            new_responses=[],
            next_question_id="nombre",
            is_complete=False,
        ),
    )

    turn: IntakeTurn = await intake_agent.process_response(session, "ehhh")

    assert turn.next_question_id == "nombre"
    assert "nombre" in turn.pending_questions
    assert session.responses == []


@pytest.mark.asyncio
async def test_process_response_marks_awaiting_image(intake_agent: IntakeAgent) -> None:
    """Si la próxima pregunta es de tipo IMAGE, `awaiting_image=True`."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    _patch_llm(
        intake_agent,
        _IntakeLLMOutput(
            assistant_message="Para la evaluación corporal voy a pedirte 4 fotos.",
            new_responses=[],
            next_question_id="foto_frente",
            is_complete=False,
        ),
    )

    turn: IntakeTurn = await intake_agent.process_response(session, "vale")

    assert turn.awaiting_image is True
    assert turn.next_question_id == "foto_frente"


@pytest.mark.asyncio
async def test_process_response_absorbs_attached_images(
    intake_agent: IntakeAgent,
) -> None:
    """Las imágenes adjuntas se imputan a la pregunta IMAGE que el agente estaba pidiendo."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    # Simula que el turno anterior pidió la foto frontal.
    session.expected_image_question_id = "foto_frente"
    _patch_llm(
        intake_agent,
        _IntakeLLMOutput(
            assistant_message="Recibida la foto frontal. Ahora la de espalda.",
            new_responses=[],
            next_question_id="foto_espalda",
            is_complete=False,
        ),
    )

    turn: IntakeTurn = await intake_agent.process_response(
        session, "aquí está", attached_images=["/tmp/frente.jpg"]
    )

    saved = next(r for r in session.responses if r.question_id == "foto_frente")
    assert saved.image_paths == ["/tmp/frente.jpg"]
    assert turn.awaiting_image is True
    # Tras absorber, la expectativa pasa a la siguiente foto (espalda).
    assert session.expected_image_question_id == "foto_espalda"


@pytest.mark.asyncio
async def test_process_response_marks_complete_when_no_pending(
    intake_agent: IntakeAgent,
) -> None:
    """Cuando ya no hay obligatorias pendientes, `is_complete=True` y se sella la fecha."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    # Pre-llenamos todas las respuestas obligatorias para forzar la completitud.
    _seed_full_answers(session)

    _patch_llm(
        intake_agent,
        _IntakeLLMOutput(
            assistant_message="¡Listo! Resumen: …",
            new_responses=[],
            next_question_id=None,
            is_complete=True,
        ),
    )

    turn: IntakeTurn = await intake_agent.process_response(session, "ok")

    assert turn.is_complete is True
    assert turn.next_question_id is None
    assert session.completed_at is not None


# ----------------------------------------------------------------- build_profile


@pytest.mark.asyncio
async def test_build_profile_raises_when_incomplete(intake_agent: IntakeAgent) -> None:
    """`build_profile` exige todas las obligatorias respondidas."""
    session: IntakeSession = await intake_agent.start_session(user_id="u")
    with pytest.raises(ValueError, match="incompleto"):
        await intake_agent.build_profile(session)


@pytest.mark.asyncio
async def test_build_profile_returns_user_profile_when_complete(
    intake_agent: IntakeAgent,
) -> None:
    """Si la sesión está completa, `build_profile` produce un `UserProfile` válido."""
    session: IntakeSession = await intake_agent.start_session(user_id="user-42")
    _seed_full_answers(session)

    profile = await intake_agent.build_profile(session)

    assert profile.id == "user-42"
    assert profile.personal.name == "Luis"
    assert profile.activity.training_days_per_week == 4
    assert profile.gym.equipment_photo_paths  # foto adjuntada


# ----------------------------------------------------------------------- helpers


def _seed_full_answers(session: IntakeSession) -> None:
    """Rellena `session.responses` con valores válidos para todas las obligatorias."""
    from src.models.questionnaire import QuestionnaireResponse, QuestionType

    defaults: dict[str, Any] = {
        "nombre": "Luis",
        "edad": 30,
        "sexo": "M",
        "altura_cm": 178.0,
        "peso_ayunas_kg": 78.5,
        "hora_levantarse": "07:00",
        "hora_acostarse": "23:30",
        "actividad_diaria": "oficina + gimnasio",
        "neat_nivel": "moderado",
        "dias_entreno_disponibles": 4,
        "dias_descanso_total": 3,
        "tipo_entreno_previo": "PPL durante un año",
        "numero_comidas_dia": 4,
        "alimentos_habituales": "arroz, pollo, huevos",
        "bebidas_habituales": ["agua", "café"],
        "agua_litros_dia": 2.5,
        "cantidad_sal": "moderada",
        "comodidad_cocinar": ["carnes", "arroz / pasta"],
        "comodidad_fuera": ["frutos secos"],
        "ventana_horaria_reducida": "no",
        "saltarse_desayuno": "no",
        "abierto_suplementos": "sí",
        "objetivo_principal": "muscle_gain",
        "objetivo_detallado": "ganar 3 kg en 4 meses",
        "material_gimnasio": "barras, mancuernas hasta 40 kg, poleas",
    }
    image_qids: dict[str, list[str]] = {
        "foto_frente": ["/tmp/frente.jpg"],
        "foto_espalda": ["/tmp/espalda.jpg"],
        "foto_perfil_izquierdo": ["/tmp/izq.jpg"],
        "foto_perfil_derecho": ["/tmp/der.jpg"],
        "equipamiento_fotos_paths": ["/tmp/gym.jpg"],
    }
    for qid, value in defaults.items():
        q = session.questionnaire.find_question(qid)
        assert q is not None, f"pregunta inesperada: {qid}"
        if q.question_type == QuestionType.IMAGE:
            continue
        session.upsert_response(QuestionnaireResponse(question_id=qid, value=value))
    for qid, paths in image_qids.items():
        session.upsert_response(QuestionnaireResponse(question_id=qid, image_paths=paths))
