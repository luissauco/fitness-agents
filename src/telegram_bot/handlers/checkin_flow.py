"""State machine del flujo de check-in bisemanal del bot de Telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

from src.models.body_assessment import BodyMeasurements
from src.models.checkin_input import CheckinInput
from src.models.progress_log import SubjectiveFeedback
from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.handlers.checkin import CHECKIN_STEPS, SUBJECTIVE_FIELDS, _ask_checkin_field
from src.telegram_bot.handlers.start import _typing_indicator
from src.telegram_bot.messages import checkin as checkin_msgs
from src.telegram_bot.services.workflow_runner import WorkflowInput, WorkflowRunner

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Pasos opcionales que aceptan saltar con texto
_SKIP_TEXT_STEPS: Final[frozenset[str]] = frozenset({"training_logs", "notes"})

# Pasos de medidas corporales opcionales y su clave en checkin_data
_MEASUREMENT_STEPS: Final[dict[str, str]] = {
    "waist": "waist_cm",
    "hips": "hip_cm",
    "arm": "arm_cm",
}


def _next_step(current: str, checkin_data: dict) -> str | None:
    """Calcula el siguiente paso en el flujo de check-in.

    Tiene en cuenta que:
    - `pain_description` solo aparece si pain=True.
    - `subjective` es un paso único que internamente itera sobre sub-campos.
    Devuelve None cuando el flujo ha terminado.
    """
    # Caso especial: dentro del paso subjective, primero agotamos los sub-campos
    if current == "subjective":
        sub_step = checkin_data.get("subjective_step")
        if sub_step is not None:
            idx = SUBJECTIVE_FIELDS.index(sub_step) if sub_step in SUBJECTIVE_FIELDS else -1
            if idx + 1 < len(SUBJECTIVE_FIELDS):
                # Todavía hay sub-campos pendientes → quedamos en "subjective"
                return "subjective"
        # Todos los sub-campos terminados → avanzar

    # Tras pain, insertar pain_description solo si pain=True
    if current == "pain":
        if checkin_data.get("pain") is True:
            return "pain_description"
        # Saltar pain_description
        idx = CHECKIN_STEPS.index("pain")
        return CHECKIN_STEPS[idx + 1] if idx + 1 < len(CHECKIN_STEPS) else None

    # Tras pain_description vamos al siguiente de "pain" en CHECKIN_STEPS
    if current == "pain_description":
        idx = CHECKIN_STEPS.index("pain")
        return CHECKIN_STEPS[idx + 1] if idx + 1 < len(CHECKIN_STEPS) else None

    # Pasos normales
    if current in CHECKIN_STEPS:
        idx = CHECKIN_STEPS.index(current)
        if idx + 1 < len(CHECKIN_STEPS):
            return CHECKIN_STEPS[idx + 1]
        return None

    return None


def _build_checkin_input(data: dict) -> CheckinInput:
    """Construye un CheckinInput desde el dict acumulado de checkin_data."""
    weights: list[float] = data.get("weights") or []

    # Peso promedio para BodyMeasurements (obligatorio)
    avg_weight: float = sum(weights) / len(weights) if weights else 0.0

    measurements = BodyMeasurements(
        weight_kg=avg_weight,
        waist_cm=data.get("waist_cm"),
        hip_cm=data.get("hip_cm"),
        arm_left_cm=data.get("arm_cm"),
    )

    subjective = SubjectiveFeedback(
        energy_level=data.get("energy") or 5,
        sleep_quality=data.get("sleep") or 5,
        hunger_level=data.get("hunger") or 5,
        motivation=data.get("motivation") or 5,
        stress_level=data.get("stress") or 5,
        soreness=data.get("doms") or 5,
        mood=data.get("mood") or 5,
        pain_or_discomfort=data.get("pain_description"),
    )

    # Adherencia: el usuario da 1-10, convertir a 0-1
    adherence_raw: int = data.get("adherence") or 5
    adherence_normalized: float = round(adherence_raw / 10.0, 2)

    photos: list[str] | None = data.get("photos") or None

    training_logs_raw = data.get("training_logs")
    training_logs: list[dict] = training_logs_raw if training_logs_raw else []

    return CheckinInput(
        weights=weights,
        measurements=measurements,
        photos=photos,
        training_logs=training_logs,
        nutrition_adherence_self_estimate=adherence_normalized,
        cheat_meals_count=data.get("cheat_meals") or 0,
        daily_steps_avg=data.get("steps") or 0,
        subjective=subjective,
        user_notes=data.get("notes"),
    )


async def _finalize_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Construye CheckinInput y ejecuta el workflow de check-in."""
    data = context.user_data["checkin_data"]
    user_id: str = context.bot_data["user_mapping"].resolve_user_id(update.effective_chat.id)
    container = context.bot_data["container"]

    checkin_input = _build_checkin_input(data)

    runner = WorkflowRunner(container.workflow, container.repos)
    image_paths = [Path(p) for p in (data.get("photos") or [])]

    await update.effective_message.reply_text(checkin_msgs.checkin_processing(), parse_mode="HTML")

    async with _typing_indicator(update, context):
        output = await runner.invoke(
            WorkflowInput(
                user_id=user_id,
                phase_hint="checkin",
                checkin_data=checkin_input,
                image_paths=image_paths,
            )
        )

    # Limpiar estado
    context.user_data["checkin_in_progress"] = False
    context.user_data["checkin_data"] = None
    context.user_data["checkin_step"] = None

    from src.telegram_bot.handlers.intake_flow import _send_workflow_output

    await _send_workflow_output(update, context, output, user_id)


async def _advance_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, current_step: str
) -> None:
    """Calcula el siguiente paso, lo guarda en user_data y pregunta el campo."""
    data = context.user_data["checkin_data"]
    next_step = _next_step(current_step, data)

    if next_step is None:
        await _finalize_checkin(update, context)
        return

    # Actualizar sub-step de subjective antes de preguntar
    if next_step == "subjective" and current_step == "subjective":
        sub_step = data.get("subjective_step", "energy")
        idx = SUBJECTIVE_FIELDS.index(sub_step) if sub_step in SUBJECTIVE_FIELDS else 0
        data["subjective_step"] = SUBJECTIVE_FIELDS[idx + 1]

    context.user_data["checkin_step"] = next_step
    await _ask_checkin_field(update, context, next_step)


@require_whitelist
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Texto libre durante el flujo de check-in."""
    if not context.user_data.get("checkin_in_progress"):
        return

    step: str = context.user_data.get("checkin_step", "")
    text: str = (update.message.text or "").strip()
    data: dict = context.user_data["checkin_data"]

    if step == "weights":
        try:
            parts = [p.strip() for p in text.replace(",", ",").split(",")]
            values = [float(p) for p in parts if p]
            if not values:
                raise ValueError("lista vacía")
        except (ValueError, AttributeError):
            await update.message.reply_text(checkin_msgs.invalid_weight(), parse_mode="HTML")
            return
        data["weights"] = values
        await _advance_step(update, context, step)

    elif step in _MEASUREMENT_STEPS:
        field_key = _MEASUREMENT_STEPS[step]
        if text.lower() in ("saltar", "s", "-"):
            data[field_key] = None
            await update.message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
            await _advance_step(update, context, step)
            return
        try:
            data[field_key] = float(text)
        except ValueError:
            await update.message.reply_text(checkin_msgs.invalid_number(), parse_mode="HTML")
            return
        await _advance_step(update, context, step)

    elif step == "steps":
        try:
            data["steps"] = int(text)
        except ValueError:
            await update.message.reply_text(checkin_msgs.invalid_number(), parse_mode="HTML")
            return
        await _advance_step(update, context, step)

    elif step == "pain_description":
        data["pain_description"] = text
        await _advance_step(update, context, step)

    elif step in _SKIP_TEXT_STEPS:
        if text.lower() in ("saltar", "s", "-"):
            data[step] = None
            await update.message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
            await _advance_step(update, context, step)
        else:
            # Guardar el texto como nota u otro valor libre
            data[step] = text
            await _advance_step(update, context, step)

    else:
        _logger.debug("texto_ignorado_en_paso step=%s text=%s", step, text)


@require_whitelist
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foto enviada durante el flujo de check-in (paso photos)."""
    if not context.user_data.get("checkin_in_progress"):
        return

    step: str = context.user_data.get("checkin_step", "")
    if step != "photos":
        return

    from src.telegram_bot.services.photo_storage import PhotoStorageService

    data: dict = context.user_data["checkin_data"]
    user_id: str = context.bot_data["user_mapping"].resolve_user_id(update.effective_chat.id)

    photo_storage = PhotoStorageService(Path("data/photos"))
    photo = update.message.photo[-1]
    saved_path = await photo_storage.save_photo(
        bot=context.bot,
        photo_file_id=photo.file_id,
        user_id=user_id,
        category="checkin",
    )

    photos: list[str] = data.get("photos") or []
    photos.append(str(saved_path))
    data["photos"] = photos

    # Con 4 fotos avanzamos automáticamente
    if len(photos) >= 4:
        await _advance_step(update, context, step)


@require_whitelist
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback queries con patrón ^checkin: durante el flujo de check-in."""
    if not context.user_data.get("checkin_in_progress"):
        return

    query = update.callback_query
    await query.answer()

    data: dict = context.user_data["checkin_data"]
    callback_data: str = query.data  # ej: "checkin:adherence:8"

    # Parsear partes tras el prefijo "checkin:"
    parts = callback_data.split(":")  # ["checkin", "adherence", "8"]

    if len(parts) < 2:
        _logger.warning("callback_malformado data=%s", callback_data)
        return

    action = parts[1]

    # --- skip de medidas opcionales: checkin:skip:waist ---
    if action == "skip" and len(parts) >= 3:
        skipped_step = parts[2]
        field_key = _MEASUREMENT_STEPS.get(skipped_step)
        if field_key:
            data[field_key] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await update.effective_message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
        await _advance_step(update, context, skipped_step)
        return

    # --- skip fotos ---
    if action == "skip_photos":
        data["photos"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await update.effective_message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
        await _advance_step(update, context, "photos")
        return

    # --- skip logs ---
    if action == "skip_logs":
        data["training_logs"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await update.effective_message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
        await _advance_step(update, context, "training_logs")
        return

    # --- skip notas ---
    if action == "skip_notes":
        data["notes"] = None
        await query.edit_message_reply_markup(reply_markup=None)
        await update.effective_message.reply_text(checkin_msgs.skip_optional(), parse_mode="HTML")
        await _advance_step(update, context, "notes")
        return

    # --- adherencia: checkin:adherence:{n} ---
    if action == "adherence" and len(parts) >= 3:
        try:
            data["adherence"] = int(parts[2])
        except ValueError:
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await _advance_step(update, context, "adherence")
        return

    # --- comidas trampa: checkin:cheat:{n} ---
    if action == "cheat" and len(parts) >= 3:
        try:
            data["cheat_meals"] = int(parts[2])
        except ValueError:
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await _advance_step(update, context, "cheat_meals")
        return

    # --- subjective: checkin:subjective:{field}:{n} ---
    if action == "subjective" and len(parts) >= 4:
        sub_field = parts[2]
        try:
            value = int(parts[3])
        except ValueError:
            return
        data[sub_field] = value
        await query.edit_message_reply_markup(reply_markup=None)
        # Avanzar sub-estado dentro de subjective
        sub_idx = SUBJECTIVE_FIELDS.index(sub_field) if sub_field in SUBJECTIVE_FIELDS else -1
        if sub_idx + 1 < len(SUBJECTIVE_FIELDS):
            data["subjective_step"] = SUBJECTIVE_FIELDS[sub_idx + 1]
            # Permanecer en paso "subjective" y preguntar el siguiente sub-campo
            await _ask_checkin_field(update, context, "subjective")
        else:
            # Último sub-campo: avanzar al siguiente paso principal
            data["subjective_step"] = None
            await _advance_step(update, context, "subjective")
        return

    # --- dolor: checkin:pain:yes / checkin:pain:no ---
    if action == "pain" and len(parts) >= 3:
        data["pain"] = parts[2] == "yes"
        await query.edit_message_reply_markup(reply_markup=None)
        await _advance_step(update, context, "pain")
        return

    _logger.warning("callback_no_manejado action=%s data=%s", action, callback_data)
