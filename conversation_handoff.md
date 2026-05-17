# HANDOFF DE SESIÓN — Bot de Telegram (2026-05-15)

> Este documento da contexto a una sesión nueva para que continúe la implementación
> exactamente donde se dejó. Léelo junto con `handoff.md` (estado general del proyecto)
> y `PROMPT_TELEGRAM_BOT_VSCODE.md` (spec completo con los 10 pasos).

---

## Estado actual

**Rama git:** `feature/telegram-bot`  
**Tests totales:** 234 pasando (215 originales + 19 nuevos de Telegram)  
**Ruff:** limpio en todos los archivos tocados

---

## Pasos completados

### PASO 1 ✅ — Dependencias, settings, estructura, DB
- `python-telegram-bot[job-queue]==21.9` instalado
- `Settings` extendido con `telegram_bot_token`, `telegram_allowed_chat_ids`, `telegram_admin_chat_id`, propiedad `allowed_chat_ids`
- `.env.example` actualizado
- Estructura `src/telegram_bot/{handlers,keyboards,services,messages,utils}/` creada (con `__init__.py`)
- Tabla `telegram_users` añadida al esquema SQLite en `src/db/connection.py`
- `TelegramUserRepository` en `src/db/repositories.py` con: `get_by_chat_id`, `register`, `is_registered`, `list_all`
- `Repositories` y `Container` en `cli/commands/factory.py` extendidos con `telegram_user` y `workflow`
- Comando `fitness telegram` añadido a `cli/fitness_cli.py`

### PASO 2 ✅ — Autenticación y mapping de usuario
- `src/telegram_bot/handlers/auth.py` → decorador `require_whitelist`
- `src/telegram_bot/services/user_mapping.py` → `UserMappingService` (síncrono, no async)
  - `resolve_user_id(chat_id)` crea o devuelve user_id único con prefijo `tg_`
  - `is_admin(chat_id)` consulta la tabla
- Tests en `tests/test_telegram_bot/test_auth.py` (9 tests)

### PASO 3 ✅ — WorkflowRunner
- `src/telegram_bot/services/workflow_runner.py`:
  - `WorkflowInput` dataclass: `user_id`, `phase_hint`, `user_message`, `image_paths`, `checkin_data`
  - `WorkflowOutput` dataclass: `current_phase`, `assistant_message`, `current_question`, `needs_user_input`, `expecting_images`, `generated_files`, `next_checkin_date`, `warnings`, `errors`, `is_complete`
  - `WorkflowRunner.invoke()`: llama `aget_state` antes de invocar (para detectar archivos nuevos), construye el input correcto según si es usuario nuevo o existente, llama `persist_artifacts` tras cada run
- Tests en `tests/test_telegram_bot/test_workflow_runner.py` (10 tests)

---

## Pasos pendientes

### PASO 4 — Handler `/start` y flujo de onboarding
Archivos a crear:
- `src/telegram_bot/handlers/start.py` — handler `/start`
- `src/telegram_bot/handlers/intake_flow.py` — mensajes/callbacks durante onboarding
- `src/telegram_bot/keyboards/question_keyboard.py` — teclado inline según `QuestionType`
- `src/telegram_bot/keyboards/common.py` — botones reutilizables
- `src/telegram_bot/services/photo_storage.py` — descarga y guarda fotos de Telegram
- `src/telegram_bot/utils/formatting.py` — helpers HTML para Telegram
- `src/telegram_bot/utils/file_sender.py` — envío de xlsx/pdf como documentos
- Tests en `tests/test_telegram_bot/test_intake_flow.py`

Lógica clave:
- `/start` llama `user_mapping.resolve_user_id(chat_id)` (síncrono, sin await)
- Si ya tiene perfil (`repos.user_profile.get(user_id)`): muestra estado
- Si es nuevo: llama `runner.invoke(WorkflowInput(user_id, phase_hint="onboarding"))`
- Cada turno: `handle_intake_message` → `WorkflowInput` con texto/imagen/callback → `runner.invoke` → `_send_workflow_output`
- Botones: `keyboard_for_question(question)` según `QuestionType` (YES_NO, SELECT, SCALE, MULTI_SELECT→None, resto→None)
- Formato callback_data: `"intake:{value}"` (ej: `"intake:yes"`, `"intake:M"`, `"intake:7"`)
- Typing indicator: context manager async que envía `send_chat_action` cada 4s

### PASO 5 — Handler `/checkin` y flujo de check-in
- `src/telegram_bot/handlers/checkin.py` — handler `/checkin`
- `src/telegram_bot/handlers/checkin_flow.py` — state machine de 10 pasos
- Pasos: weights → measurements → photos → adherence → cheat_meals → steps → subjective → pain → training_logs → notes
- Estado del flujo en `context.user_data["checkin_in_progress"]`, `["checkin_step"]`, `["checkin_data"]`
- Al final: construye `CheckinInput` y llama `runner.invoke` con `checkin_data`
- Tests en `tests/test_telegram_bot/test_checkin_flow.py`

### PASO 6 — Handlers auxiliares
- `src/telegram_bot/handlers/status.py` — `/status` con formato HTML
- `src/telegram_bot/handlers/export.py` — `/export` con submenú inline
- `src/telegram_bot/handlers/help.py` — `/help` estático
- Handler fallback para mensajes fuera de flujo

### PASO 7 — Scheduler de recordatorio de check-in
- `src/telegram_bot/services/scheduler.py` → `CheckinReminderScheduler`
  - `schedule_checkin_reminder(user_id, chat_id, checkin_date)` → job único a las 10:00
  - Cancela job previo si existe (mismo nombre `checkin_reminder_{user_id}`)
  - `restore_scheduled_reminders()` al arrancar: relée todos los chat_ids de la BD y reprograma
- Tests en `tests/test_telegram_bot/test_scheduler.py`

### PASO 8 — App principal
- `src/telegram_bot/app.py` con `build_application()` y `run_bot()`
- `post_init`: abre `open_async_checkpointer`, compila workflow CON checkpointer, crea `WorkflowRunner`, `UserMappingService`, `CheckinReminderScheduler`; todo en `bot_data`
- Registra handlers en orden: commands, callbacks (`^intake:`, `^checkin:`, `^export:`), messages (foto/texto → routing por `context.user_data["checkin_in_progress"]`)
- `_global_error_handler` → notifica al admin
- Tests en `tests/test_telegram_bot/test_app.py`

### PASO 9 — Mensajes en español
- `src/telegram_bot/messages/intake.py`, `checkin.py`, `status.py`, `errors.py`
- HTML puro (no Markdown), tuteo, máximo 1 emoji por mensaje

### PASO 10 — Documentación
- Sección "Bot de Telegram" en `README.md`
- Actualizar `handoff.md` con sección 13 "Interfaz Telegram"

---

## Adaptaciones importantes (plan vs código real)

| Plan dice | Código real | Resolución |
|-----------|-------------|------------|
| `build_container(settings)` | `build_container()` — sin args | El bot usa `container.settings` |
| `container.workflow_runner` en Container | WorkflowRunner se crea en `post_init` (necesita checkpointer async) | `bot_data["workflow_runner"]` |
| `UserMappingService.resolve_user_id` es async | Es **síncrono** (SQLite es síncrono) | Llamar sin `await` |
| Checkpointer en Container | El bot abre `open_async_checkpointer` en `post_init` y lo mantiene vivo | Ver PASO 8 |

---

## Arquitectura del bot en `bot_data`

```python
bot_data = {
    "settings": Settings,                    # get_settings()
    "container": Container,                  # build_container()
    "user_mapping": UserMappingService,      # repo=container.repos.telegram_user
    "workflow_runner": WorkflowRunner,       # workflow compilado CON checkpointer
    "scheduler": CheckinReminderScheduler,   # job_queue + repos
}
```

El estado **por usuario** (flujo de checkin en curso, pasos, datos parciales) va en `context.user_data` (gestionado por python-telegram-bot, aislado por chat_id).

---

## Convenciones a respetar

- Logging stdlib: `_logger: Final[logging.Logger] = logging.getLogger(__name__)`
- Type hints obligatorios, docstrings en español
- Ruff solo sobre los archivos que tocas: `uv run ruff check <ruta> && uv run ruff format <ruta>`
- Tests con pytest-asyncio (`asyncio_mode=auto` ya configurado en pyproject.toml)
- Sin `print()`, sin loguru
- No modificar agentes, generadores ni grafo

---

## Cómo verificar que todo sigue funcionando

```bash
# Tests completos
uv run pytest tests/ -q

# Solo bot
uv run pytest tests/test_telegram_bot/ -v

# Ruff sobre el módulo
uv run ruff check src/telegram_bot/ tests/test_telegram_bot/
```

## Archivos creados/modificados en esta sesión

```
MODIFICADOS:
  src/config/settings.py          ← 3 campos telegram + propiedad allowed_chat_ids
  src/db/connection.py            ← tabla telegram_users en _SCHEMA_SQL
  src/db/repositories.py          ← TelegramUserRepository al final
  cli/commands/factory.py         ← TelegramUserRepository en Repositories, workflow en Container
  cli/fitness_cli.py              ← comando telegram
  .env.example                    ← variables TELEGRAM_*
  pyproject.toml (indirecto)      ← uv añadió python-telegram-bot

CREADOS:
  src/telegram_bot/__init__.py
  src/telegram_bot/handlers/__init__.py
  src/telegram_bot/handlers/auth.py
  src/telegram_bot/keyboards/__init__.py
  src/telegram_bot/services/__init__.py
  src/telegram_bot/services/user_mapping.py
  src/telegram_bot/services/workflow_runner.py
  src/telegram_bot/messages/__init__.py
  src/telegram_bot/utils/__init__.py
  tests/test_telegram_bot/__init__.py
  tests/test_telegram_bot/test_auth.py
  tests/test_telegram_bot/test_workflow_runner.py
```
