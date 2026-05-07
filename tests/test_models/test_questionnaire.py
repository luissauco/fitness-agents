"""Tests del cuestionario default y sus modelos de respuesta."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.questionnaire import (
    Question,
    Questionnaire,
    QuestionnaireResponse,
    QuestionType,
)

EXPECTED_BLOCKS = [
    "datos_personales",
    "actividad_entrenamiento",
    "nutricion_actual",
    "preferencias",
    "objetivos",
    "equipamiento_fotos",
]


def test_default_questionnaire_has_all_blocks() -> None:
    q = Questionnaire.get_default()
    assert set(q.blocks.keys()) == set(EXPECTED_BLOCKS)


def test_default_questionnaire_block_count() -> None:
    q = Questionnaire.get_default()
    assert len(q.blocks) == len(EXPECTED_BLOCKS)


def test_all_questions_count() -> None:
    q = Questionnaire.get_default()
    assert len(q.all_questions()) >= 30


def test_required_questions_are_majority() -> None:
    q = Questionnaire.get_default()
    all_qs = q.all_questions()
    required_ids = q.required_question_ids()
    assert len(required_ids) > len(all_qs) // 2


def test_select_question_requires_options() -> None:
    with pytest.raises(ValidationError):
        Question(
            id="test-select",
            block="test",
            text="¿Cuál es tu objetivo?",
            question_type=QuestionType.SELECT,
        )


def test_non_select_with_options_raises() -> None:
    with pytest.raises(ValidationError):
        Question(
            id="test-text",
            block="test",
            text="Describe tu situación.",
            question_type=QuestionType.TEXT,
            options=["opción a", "opción b"],
        )


def test_missing_required_when_fully_answered() -> None:
    q = Questionnaire.get_default()
    responses = [
        QuestionnaireResponse(question_id=qid, value="respuesta")
        for qid in q.required_question_ids()
    ]
    assert q.missing_required(responses) == []


def test_missing_required_detects_gaps() -> None:
    q = Questionnaire.get_default()
    required = q.required_question_ids()
    # responde todos excepto el primero requerido
    responses = [QuestionnaireResponse(question_id=qid, value="respuesta") for qid in required[1:]]
    missing = q.missing_required(responses)
    assert required[0] in missing


def test_missing_required_ignores_optional_if_not_answered() -> None:
    q = Questionnaire.get_default()
    # cuestionario con solo las preguntas requeridas respondidas
    required = q.required_question_ids()
    responses = [QuestionnaireResponse(question_id=qid, value="x") for qid in required]
    # No debe reportar ninguna falta aunque las opcionales estén sin responder
    assert q.missing_required(responses) == []


def test_find_question_by_id() -> None:
    q = Questionnaire.get_default()
    found = q.find_question("edad")
    assert found is not None
    assert found.id == "edad"
    assert found.question_type == QuestionType.NUMBER


def test_find_question_not_found() -> None:
    q = Questionnaire.get_default()
    assert q.find_question("pregunta-inexistente") is None


def test_all_questions_preserves_block_order() -> None:
    q = Questionnaire.get_default()
    all_qs = q.all_questions()
    # El primer bloque es datos_personales → primer question_id debe ser "nombre"
    assert all_qs[0].block == "datos_personales"
