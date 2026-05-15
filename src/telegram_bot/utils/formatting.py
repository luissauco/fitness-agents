"""Utilidades de formateo HTML para mensajes de Telegram."""

from __future__ import annotations


def escape_html(text: str) -> str:
    """Escapa caracteres especiales HTML: &, <, >."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bold(text: str) -> str:
    """Envuelve texto en <b>texto</b>."""
    return f"<b>{text}</b>"


def code_block(text: str) -> str:
    """Envuelve texto en <pre>texto</pre>."""
    return f"<pre>{text}</pre>"
