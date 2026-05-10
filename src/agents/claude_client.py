"""Cliente async sobre el SDK de Anthropic con structured outputs y reintentos.

Encapsula tres operaciones:

- `generate_structured`: fuerza un output JSON validado contra un modelo Pydantic
  usando el patrón de `tool_use` con un único tool obligatorio. Si la validación
  Pydantic falla, reintenta con el error inyectado en el siguiente turno.
- `generate_text`: respuesta libre como `str` (para flujos conversacionales).
- `generate_stream`: iterador asíncrono de chunks de texto.

Soporta mensajes multimodales (texto + imágenes) y extended thinking (Opus 4.x).
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Final, TypeVar

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import Settings

_logger: Final[logging.Logger] = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Nombre fijo del tool que fuerza structured output.
_STRUCTURED_TOOL: Final[str] = "submit_response"

# Errores transitorios que merecen reintento exponencial.
_RETRYABLE_API_ERRORS: Final[tuple[type[Exception], ...]] = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class ClaudeStructuredOutputError(RuntimeError):
    """Se lanzó cuando Claude no devolvió un tool_use válido tras los reintentos."""


def _normalize_user_content(
    user_message: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convierte un mensaje de usuario en una lista de bloques multimodales."""
    if isinstance(user_message, str):
        return [{"type": "text", "text": user_message}]
    return list(user_message)


def image_block_from_path(image_path: str | Path) -> dict[str, Any]:
    """Construye un bloque multimodal de imagen leyendo el fichero a base64."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe la imagen: {path}")
    media_type, _ = mimetypes.guess_type(str(path))
    if media_type is None or not media_type.startswith("image/"):
        media_type = "image/jpeg"
    data: str = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _extract_tool_input(message: anthropic.types.Message) -> dict[str, Any] | None:
    """Devuelve el input del primer bloque `tool_use` de la respuesta, si existe."""
    for block in message.content:
        if getattr(block, "type", None) == "tool_use":
            raw: Any = getattr(block, "input", None)
            if isinstance(raw, dict):
                return raw
    return None


def _extract_text(message: anthropic.types.Message) -> str:
    """Concatena los bloques de texto de la respuesta."""
    parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


class ClaudeClient:
    """Wrapper async sobre `AsyncAnthropic` con reintentos y logging estructurado."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa el cliente con la API key y el timeout configurados."""
        self._settings: Settings = settings
        self._client: AsyncAnthropic = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
            timeout=float(settings.CLAUDE_REQUEST_TIMEOUT_S),
        )

    @property
    def raw(self) -> AsyncAnthropic:
        """Acceso al cliente Anthropic subyacente (uso muy puntual)."""
        return self._client

    # ------------------------------------------------------------- Structured

    async def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str | list[dict[str, Any]],
        response_model: type[T],
        max_tokens: int = 8192,
        temperature: float = 0.7,
        thinking: bool = False,
        thinking_budget_tokens: int = 5000,
    ) -> T:
        """Genera un output validado contra `response_model` (tool_use forzado).

        Reintenta hasta `settings.CLAUDE_MAX_RETRIES` veces:
            - Si falla la API por error transitorio, con backoff exponencial.
            - Si falla la validación Pydantic, reintenta inyectando el error en
              el historial de conversación para que Claude corrija el JSON.
        """
        tool: dict[str, Any] = {
            "name": _STRUCTURED_TOOL,
            "description": (
                f"Devuelve la respuesta como JSON conforme al schema de "
                f"{response_model.__name__}. Llama a este tool exactamente una vez."
            ),
            "input_schema": response_model.model_json_schema(),
        }
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _normalize_user_content(user_message)},
        ]
        last_error: str = ""

        for attempt in range(1, self._settings.CLAUDE_MAX_RETRIES + 1):
            response: anthropic.types.Message = await self._call_with_retry(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=[tool],
                tool_choice={"type": "tool", "name": _STRUCTURED_TOOL},
                thinking=thinking,
                thinking_budget_tokens=thinking_budget_tokens,
            )

            tool_input: dict[str, Any] | None = _extract_tool_input(response)
            if tool_input is None:
                last_error = (
                    "La respuesta no incluye ningún bloque `tool_use`; debes invocar "
                    f"el tool '{_STRUCTURED_TOOL}' con los campos requeridos."
                )
                _logger.warning(
                    "claude_client.no_tool_use",
                    extra={"model": model, "attempt": attempt},
                )
            else:
                try:
                    return response_model.model_validate(tool_input)
                except ValidationError as exc:
                    last_error = (
                        "El JSON anterior no validó contra el schema. "
                        f"Errores Pydantic: {exc.errors()}. "
                        "Vuelve a llamar al tool corrigiendo exclusivamente esos campos."
                    )
                    _logger.warning(
                        "claude_client.validation_failed",
                        extra={"model": model, "attempt": attempt, "errors": exc.errors()},
                    )

            # Inyecta el error en el historial para el siguiente intento.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": last_error})

        raise ClaudeStructuredOutputError(
            f"Tras {self._settings.CLAUDE_MAX_RETRIES} intentos no se obtuvo un "
            f"{response_model.__name__} válido. Último error: {last_error}"
        )

    # ------------------------------------------------------------- Texto libre

    async def generate_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str | list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Genera texto libre. Útil para agentes conversacionales."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _normalize_user_content(user_message)},
        ]
        response: anthropic.types.Message = await self._call_with_retry(
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return _extract_text(response)

    # ------------------------------------------------------------- Streaming

    async def generate_stream(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str | list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Genera respuesta en streaming, yieldeando chunks de texto."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _normalize_user_content(user_message)},
        ]
        async with self._client.messages.stream(
            model=model,
            system=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            async for chunk in stream.text_stream:
                yield chunk

    # ------------------------------------------------------------- Internos

    async def _call_with_retry(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        thinking: bool = False,
        thinking_budget_tokens: int = 5000,
    ) -> anthropic.types.Message:
        """Llama a `messages.create` con backoff exponencial sobre errores transitorios."""
        kwargs: dict[str, Any] = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if thinking:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            }
            # Extended thinking exige temperature=1.
            kwargs["temperature"] = 1.0

        retrier: AsyncRetrying = AsyncRetrying(
            stop=stop_after_attempt(self._settings.CLAUDE_MAX_RETRIES),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            retry=retry_if_exception_type(_RETRYABLE_API_ERRORS),
            reraise=True,
        )

        async for attempt in retrier:
            with attempt:
                start: float = time.perf_counter()
                response: anthropic.types.Message = await self._client.messages.create(**kwargs)
                elapsed_ms: int = int((time.perf_counter() - start) * 1000)
                _logger.info(
                    "claude_client.call",
                    extra={
                        "model": model,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "elapsed_ms": elapsed_ms,
                        "stop_reason": response.stop_reason,
                    },
                )
                return response

        raise RuntimeError("retrier finalizó sin respuesta (no debería ocurrir).")
