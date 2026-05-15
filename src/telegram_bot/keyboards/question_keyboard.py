"""Teclados inline generados a partir del tipo de pregunta del cuestionario."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.models.questionnaire import Question, QuestionType


def keyboard_for_question(question: Question) -> InlineKeyboardMarkup | None:
    """Devuelve teclado inline para preguntas cerradas, None para abiertas.

    - YES_NO  → 2 botones: «Sí» (intake:yes) / «No» (intake:no)
    - SELECT  → una opción por fila con callback_data=«intake:{opt}»
    - SCALE   → escala 1-10 en dos filas (1-5 y 6-10)
    - resto   → None (respuesta de texto libre)
    """
    qt = question.question_type

    if qt == QuestionType.YES_NO:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Sí", callback_data="intake:yes"),
                    InlineKeyboardButton("No", callback_data="intake:no"),
                ]
            ]
        )

    if qt == QuestionType.SELECT and question.options:
        rows = [
            [InlineKeyboardButton(opt, callback_data=f"intake:{opt}")] for opt in question.options
        ]
        return InlineKeyboardMarkup(rows)

    if qt == QuestionType.SCALE:
        row_1 = [InlineKeyboardButton(str(i), callback_data=f"intake:{i}") for i in range(1, 6)]
        row_2 = [InlineKeyboardButton(str(i), callback_data=f"intake:{i}") for i in range(6, 11)]
        return InlineKeyboardMarkup([row_1, row_2])

    return None
