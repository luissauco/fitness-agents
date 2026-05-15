"""Teclados inline reutilizables para el bot de Telegram."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def skip_button() -> InlineKeyboardMarkup:
    """Botón 'Saltar' con callback_data='intake:skip'."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("Saltar", callback_data="intake:skip")]])


def yes_no_buttons() -> InlineKeyboardMarkup:
    """Botones Sí/No reutilizables."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Sí", callback_data="intake:yes"),
                InlineKeyboardButton("No", callback_data="intake:no"),
            ]
        ]
    )
