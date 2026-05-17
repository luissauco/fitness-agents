"""Tests del wrapper `ClaudeClient`.

Mockean `AsyncAnthropic.messages.create` con un `AsyncMock` para no consumir
red ni tokens. Verifican structured outputs, reintentos ante validación fallida
y manejo de imágenes en `user_message`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, Field

from src.agents.claude_client import (
    ClaudeClient,
    ClaudeStructuredOutputError,
    image_block_from_path,
)
from src.config.settings import Settings

# --------------------------------------------------------------------- Helpers


class _Plan(BaseModel):
    """Modelo Pydantic mínimo usado como `response_model` en los tests."""

    title: str
    days: int = Field(..., ge=1, le=10)


def _fake_message(
    *,
    tool_input: dict[str, Any] | None = None,
    text: str = "",
    input_tokens: int = 10,
    output_tokens: int = 20,
    stop_reason: str = "end_turn",
) -> SimpleNamespace:
    """Construye una respuesta `Message` con la estructura mínima que el cliente lee."""
    blocks: list[SimpleNamespace] = []
    if tool_input is not None:
        blocks.append(SimpleNamespace(type="tool_use", name="submit_response", input=tool_input))
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


def _make_client(settings: Settings) -> tuple[ClaudeClient, AsyncMock]:
    """Crea un `ClaudeClient` con `messages.create` mockeado. Devuelve (cliente, mock)."""
    client = ClaudeClient(settings)
    create_mock = AsyncMock()
    client._client.messages.create = create_mock  # type: ignore[method-assign]
    return client, create_mock


# ------------------------------------------------------------------ generate_structured


@pytest.mark.asyncio
async def test_generate_structured_returns_validated_model(settings: Settings) -> None:
    """Si Claude devuelve tool_use válido al primer intento, retorna el modelo."""
    client, create_mock = _make_client(settings)
    create_mock.return_value = _fake_message(tool_input={"title": "Plan A", "days": 5})

    plan: _Plan = await client.generate_structured(
        model="claude-sonnet-4-6",
        system_prompt="eres un planificador",
        user_message="dame un plan",
        response_model=_Plan,
    )

    assert plan == _Plan(title="Plan A", days=5)
    assert create_mock.await_count == 1
    # tool_choice fuerza el tool y debe haber un único tool en la llamada.
    call_kwargs = create_mock.await_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "submit_response"}
    assert len(call_kwargs["tools"]) == 1
    assert call_kwargs["tools"][0]["name"] == "submit_response"


@pytest.mark.asyncio
async def test_generate_structured_retries_on_validation_error(settings: Settings) -> None:
    """Si el primer JSON no valida, reintenta inyectando el error y luego acepta."""
    client, create_mock = _make_client(settings)
    create_mock.side_effect = [
        # `days=42` viola el límite ge=1, le=10 del modelo.
        _fake_message(tool_input={"title": "Bad", "days": 42}),
        _fake_message(tool_input={"title": "Bad", "days": 4}),
    ]

    plan: _Plan = await client.generate_structured(
        model="claude-sonnet-4-6",
        system_prompt="sys",
        user_message="msg",
        response_model=_Plan,
    )

    assert plan.days == 4
    assert create_mock.await_count == 2
    # En el segundo intento, los mensajes incluyen la corrección con el error.
    second_call_messages = create_mock.await_args_list[1].kwargs["messages"]
    assert len(second_call_messages) == 3  # user inicial + assistant + user con error
    assert "Errores Pydantic" in second_call_messages[-1]["content"]


@pytest.mark.asyncio
async def test_generate_structured_raises_after_exhausting_retries(
    settings: Settings,
) -> None:
    """Si tras todos los intentos no hay tool_use válido, lanza error tipado."""
    client, create_mock = _make_client(settings)
    # Siempre devuelve respuesta sin tool_use.
    create_mock.return_value = _fake_message(text="no llamo al tool")

    with pytest.raises(ClaudeStructuredOutputError):
        await client.generate_structured(
            model="claude-sonnet-4-6",
            system_prompt="sys",
            user_message="msg",
            response_model=_Plan,
        )

    assert create_mock.await_count == settings.CLAUDE_MAX_RETRIES


@pytest.mark.asyncio
async def test_generate_structured_passes_multimodal_content(settings: Settings) -> None:
    """Si `user_message` ya es lista de bloques, se reenvía tal cual al SDK."""
    client, create_mock = _make_client(settings)
    create_mock.return_value = _fake_message(tool_input={"title": "P", "days": 3})

    multimodal: list[dict[str, Any]] = [
        {"type": "text", "text": "analiza esta foto"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAA="},
        },
    ]
    await client.generate_structured(
        model="claude-sonnet-4-6",
        system_prompt="sys",
        user_message=multimodal,
        response_model=_Plan,
    )

    sent_content = create_mock.await_args.kwargs["messages"][0]["content"]
    assert sent_content == multimodal


@pytest.mark.asyncio
async def test_generate_structured_extended_thinking_overrides_temperature(
    settings: Settings,
) -> None:
    """Con thinking=True el cliente fuerza temperature=1 y añade el bloque thinking."""
    client, create_mock = _make_client(settings)
    create_mock.return_value = _fake_message(tool_input={"title": "T", "days": 2})

    await client.generate_structured(
        model="claude-opus-4-7",
        system_prompt="sys",
        user_message="msg",
        response_model=_Plan,
        temperature=0.3,
        thinking=True,
    )

    kwargs = create_mock.await_args.kwargs
    assert "temperature" not in kwargs
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "high"}


# ---------------------------------------------------------------------- text


@pytest.mark.asyncio
async def test_generate_text_returns_concatenated_text(settings: Settings) -> None:
    """`generate_text` concatena los bloques de texto y no envía tools."""
    client, create_mock = _make_client(settings)
    create_mock.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="hola "),
            SimpleNamespace(type="text", text="mundo"),
        ],
        usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        stop_reason="end_turn",
    )

    out: str = await client.generate_text(
        model="claude-sonnet-4-6",
        system_prompt="sys",
        user_message="msg",
    )

    assert out == "hola mundo"
    assert "tools" not in create_mock.await_args.kwargs
    assert "tool_choice" not in create_mock.await_args.kwargs


# --------------------------------------------------------------- image helper


def test_image_block_from_path(tmp_path: Path) -> None:
    """`image_block_from_path` produce el bloque base64 con media_type correcto."""
    img: Path = tmp_path / "foto.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg_bytes")

    block: dict[str, Any] = image_block_from_path(img)

    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/jpeg"
    assert isinstance(block["source"]["data"], str) and block["source"]["data"]


def test_image_block_from_path_missing_file(tmp_path: Path) -> None:
    """Lanza FileNotFoundError si la imagen no existe."""
    with pytest.raises(FileNotFoundError):
        image_block_from_path(tmp_path / "no_existe.jpg")
