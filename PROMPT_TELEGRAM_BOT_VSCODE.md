# PROMPT PARA CREAR LA UI DEL PROYECTO COMO BOT DE TELEGRAM

> Pega este prompt en Claude Code dentro de tu proyecto fitness-agents.
> Modelo recomendado: **Claude Sonnet 4.6 con effort medium**.
> Claude Code lee tu CLAUDE.md y `handoff.md` con el estado real del proyecto.

---

## DECISIONES DE DISEÑO (confirmadas)

- **Modo**: privado para ti + 2-3 personas más. Whitelist de chat IDs en `.env` (CSV).
- **Cuestionario**: una pregunta a la vez, conversación natural. Cuando la pregunta es cerrada (sí/no, select, escala), se acompaña con botones inline para mejorar UX, pero el flujo sigue siendo pregunta → respuesta → siguiente pregunta.
- **Notificaciones**: únicamente recordatorio de check-in cada 14 días. Sin recordatorios diarios ni de otro tipo.

---

## PROMPT:

````
Vamos a construir la UI del sistema como bot de Telegram. Es la última fase del proyecto: ya tenemos agentes funcionando, generadores de archivos y CLI end-to-end. Ahora exponemos todo eso por Telegram.

## CONTEXTO DEL PROYECTO

Lee primero `handoff.md` en la raíz del proyecto. Es la fuente de verdad del estado actual: arquitectura, modelos reales, grafo LangGraph, convenciones. Si algo en este prompt contradice handoff.md o el código, gana el código — verifica siempre contra `src/models/`, `src/graph/state.py` y los agentes.

Resumen relevante para esta fase:
- Sistema multi-agente funcionando end-to-end por CLI (`fitness start`, `fitness checkin`, etc.)
- Orquestador LangGraph con checkpointer SQLite (estado persistente entre invocaciones)
- 5 agentes: intake (conversacional, una pregunta por turno), assessment, training, nutrition, progress
- Generadores que producen .xlsx y .pdf en `output/`
- Repositorios en `src/db/` para persistir UserProfile, Mesocycle, NutritionPlan, BodyAssessment, ProgressLog
- `cli/commands/factory.py` ya tiene `build_container()` y `persist_artifacts(state, repos)` — REUTILIZA ESTO

## OBJETIVO

Bot de Telegram que permita:
1. Iniciar cuestionario conversacional (`/start`)
2. Subir fotos corporales y del gimnasio
3. Recibir el Excel del mesociclo y los PDFs como archivos descargables
4. Hacer check-in bisemanal (`/checkin`) con foto, peso, medidas y feedback
5. Recibir recordatorio cada 14 días del próximo check-in
6. Consultar estado (`/status`), reexportar archivos (`/export`), pedir ayuda (`/help`)

El bot es una capa de presentación. NO duplica lógica de los agentes ni del grafo. Llama al workflow LangGraph existente y traduce su estado a mensajes de Telegram.

## DECISIONES YA TOMADAS

1. **Modo de uso**: privado con whitelist de chat IDs en `.env` (TELEGRAM_ALLOWED_CHAT_IDS como CSV). Soporta múltiples usuarios autorizados (yo + 2-3 más), cada uno con su propio user_id y workflow state independiente.

2. **Cuestionario**: una pregunta a la vez, flujo conversacional puro. NADA de presentar bloques completos ni listas de preguntas. El IntakeAgent ya está diseñado así (turno por turno). La UI simplemente acompaña cada pregunta con botones inline cuando la pregunta es cerrada (yes/no, select, escala 1-10). Para preguntas abiertas (texto, número, hora), el usuario escribe libremente.

3. **Notificaciones**: ÚNICAMENTE recordatorio de check-in cuando llegue `next_checkin_date`. Sin recordatorios diarios, sin alertas de pasos, sin nada más. El scheduler se limita a un job por usuario que se reprograma cada vez que se completa un check-in.

4. **Mapping chat_id → user_id**: tabla `telegram_users(chat_id, user_id, created_at)` en SQLite. Cada chat_id del whitelist se asocia a un user_id en el primer `/start`.

## QUÉ NECESITO

Sigue este orden EXACTO. Espera mi confirmación entre pasos.

---

### PASO 1: Dependencias y configuración

**1.1 Añadir dependencias** (uv):

```bash
uv add python-telegram-bot[job-queue]==21.9
```

`[job-queue]` incluye APScheduler para el recordatorio de check-in. Versión 21.x (async nativo).

**1.2 Variables de entorno nuevas** (añadir a `.env.example` y a `src/config/settings.py`):

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=    # CSV de chat IDs autorizados, ej: 123456789,987654321,555444333
TELEGRAM_ADMIN_CHAT_ID=        # chat ID que recibe errores y logs
```

Extender `Settings`:

```python
class Settings(BaseSettings):
    # ... existentes ...
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""  # CSV
    telegram_admin_chat_id: str = ""
    
    @property
    def allowed_chat_ids(self) -> set[int]:
        if not self.telegram_allowed_chat_ids:
            return set()
        return {int(x.strip()) for x in self.telegram_allowed_chat_ids.split(",") if x.strip()}
```

**1.3 Estructura del módulo**:

```
src/telegram_bot/
├── __init__.py
├── app.py                    # ApplicationBuilder y main()
├── handlers/
│   ├── __init__.py
│   ├── auth.py               # decorador de whitelist
│   ├── start.py              # /start → onboarding
│   ├── checkin.py            # /checkin → check-in bisemanal
│   ├── status.py             # /status
│   ├── export.py             # /export
│   ├── help.py               # /help
│   ├── intake_flow.py        # conversación de cuestionario (1 pregunta/turno)
│   └── checkin_flow.py       # conversación de check-in
├── keyboards/
│   ├── __init__.py
│   ├── question_keyboard.py  # genera teclado inline según QuestionType
│   ├── checkin.py            # botones para check-in
│   └── common.py             # botones reutilizables (sí/no, saltar, escala)
├── services/
│   ├── __init__.py
│   ├── user_mapping.py       # chat_id ↔ user_id
│   ├── photo_storage.py      # descarga y guarda fotos
│   ├── workflow_runner.py    # wrapper sobre el workflow LangGraph
│   └── scheduler.py          # recordatorio de check-in (único tipo)
├── messages/                 # plantillas de texto en español
│   ├── __init__.py
│   ├── intake.py
│   ├── checkin.py
│   ├── status.py
│   └── errors.py
└── utils/
    ├── __init__.py
    ├── formatting.py         # helpers de markdown/HTML para Telegram
    └── file_sender.py        # envío de xlsx/pdf como documentos
```

**1.4 Tabla de mapping en SQLite**:

Migración nueva en `src/db/` (no rompe nada existente):

```sql
CREATE TABLE IF NOT EXISTS telegram_users (
    chat_id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE
);
```

Repository: `src/db/repositories.py` añade `TelegramUserRepository` con:
- `get_by_chat_id(chat_id) -> tuple[str, bool] | None` (user_id, is_admin)
- `register(chat_id, user_id, is_admin=False)`
- `is_registered(chat_id) -> bool`
- `list_all() -> list[tuple[int, str]]` (para restore del scheduler)

Verifica esto contra el patrón real de repositorios en el proyecto antes de implementar.

**1.5 Punto de entrada CLI**:

Añade a `cli/fitness_cli.py` un comando:

```python
@app.command()
def telegram() -> None:
    """Lanza el bot de Telegram."""
    from src.telegram_bot.app import run_bot
    run_bot()
```

Permite lanzar el bot con `uv run fitness telegram`.

---

### PASO 2: Autenticación y mapping de usuario

**2.1 Decorador de whitelist** (`handlers/auth.py`):

```python
import logging
from functools import wraps
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

_logger: Final[logging.Logger] = logging.getLogger(__name__)


def require_whitelist(func):
    """Decorador que bloquea acceso a chat_ids no autorizados."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        settings = context.bot_data["settings"]
        
        if chat_id not in settings.allowed_chat_ids:
            _logger.warning("Acceso denegado a chat_id=%s", chat_id)
            await update.message.reply_text(
                "No tienes acceso a este bot. Contacta con el administrador."
            )
            return
        
        return await func(update, context)
    return wrapper
```

**2.2 Servicio de mapping** (`services/user_mapping.py`):

```python
class UserMappingService:
    """Resuelve chat_id de Telegram a user_id del sistema."""
    
    def __init__(self, repo: TelegramUserRepository, settings: Settings):
        self.repo = repo
        self.settings = settings
    
    async def resolve_user_id(self, chat_id: int) -> str:
        """
        Si el chat_id ya está registrado, devuelve su user_id.
        Si es la primera vez, crea un nuevo user_id único (slug + uuid corto).
        Cada chat_id tiene su propio user_id y workflow state independiente.
        """
        ...
    
    async def is_admin(self, chat_id: int) -> bool:
        ...
```

Importante: como hay múltiples usuarios autorizados, el `user_id` debe ser único por chat_id. El thread_id del checkpointer LangGraph será el `user_id`, garantizando aislamiento entre usuarios.

**2.3 Inyección en context.bot_data**:

En `app.py`, antes de arrancar el bot:

```python
async def post_init(application: Application) -> None:
    """Inicializa dependencias compartidas en bot_data."""
    settings = build_settings()
    container = build_container(settings)  # reutiliza factory.py
    
    application.bot_data["settings"] = settings
    application.bot_data["container"] = container
    application.bot_data["user_mapping"] = UserMappingService(
        container.repos.telegram_user, settings
    )
```

Todos los handlers acceden a estas dependencias vía `context.bot_data`. El estado per-usuario va en `context.user_data` (gestionado automáticamente por python-telegram-bot, aislado por chat).

**Tests**: `tests/test_telegram_bot/test_auth.py`:
- chat_id en whitelist → handler ejecutado
- chat_id fuera de whitelist → handler bloqueado, mensaje correcto
- Mapping: primer /start → registra; segundo → devuelve mismo user_id
- Dos chat_ids distintos → user_ids distintos (aislamiento entre usuarios)

---

### PASO 3: WorkflowRunner — wrapper sobre LangGraph

Esto es el corazón de la integración. Telegram NO conoce el grafo: solo manda inputs al runner y recibe outputs traducibles a mensajes.

**3.1 Modelo de input/output** (`services/workflow_runner.py`):

```python
@dataclass
class WorkflowInput:
    """Input genérico para una invocación del workflow."""
    user_id: str
    phase_hint: Literal["onboarding", "checkin"] | None = None
    user_message: str | None = None
    image_paths: list[Path] = field(default_factory=list)
    checkin_data: CheckinInput | None = None


@dataclass
class WorkflowOutput:
    """Lo que el runner devuelve para que el handler lo traduzca a Telegram."""
    current_phase: str
    assistant_message: str | None       # pregunta o feedback del agente
    current_question: Question | None   # si está en intake, la pregunta actual
    needs_user_input: bool              # si está esperando respuesta
    expecting_images: bool              # si está esperando fotos
    generated_files: list[Path]         # archivos nuevos a enviar
    next_checkin_date: date | None      # para programar recordatorio
    warnings: list[str]
    errors: list[str]
    is_complete: bool                   # fase completada
```

**3.2 Implementación**:

```python
class WorkflowRunner:
    """
    Wrapper sobre el grafo LangGraph que ofrece una API más simple para Telegram.
    Mantiene el estado per-user a través del checkpointer SQLite del grafo.
    """
    
    def __init__(self, container: Container, settings: Settings):
        self.workflow = container.workflow  # ya compilado con checkpointer
        self.repos = container.repos
        self.settings = settings
    
    async def invoke(self, input: WorkflowInput) -> WorkflowOutput:
        """
        Ejecuta el workflow con el input dado.
        
        - Carga el estado actual desde el checkpointer (thread_id = user_id)
        - Aplica el input (mensaje, imágenes, checkin_data)
        - Ejecuta ainvoke
        - Traduce el estado final a WorkflowOutput
        """
        config = {"configurable": {"thread_id": input.user_id}}
        
        # Estado actual o inicial
        current_state = await self._get_or_init_state(input.user_id, config)
        
        # Aplicar input al estado
        updated_state = self._merge_input(current_state, input)
        
        # Ejecutar
        final_state = await self.workflow.ainvoke(updated_state, config=config)
        
        # Persistir artefactos (usa la función ya existente)
        persist_artifacts(final_state, self.repos)
        
        return self._to_output(final_state)
    
    def _merge_input(self, state: FitnessState, input: WorkflowInput) -> dict:
        """
        Construye el dict de update para el estado según el input.
        - Si hay user_message: añade a messages
        - Si hay image_paths: añade según la fase (body_photo_paths, equipment, checkin photos)
        - Si hay checkin_data: lo pone en pending_checkin_data
        """
        ...
    
    def _to_output(self, state: FitnessState) -> WorkflowOutput:
        """Traduce el FitnessState al WorkflowOutput."""
        # Determina assistant_message según la fase:
        # - onboarding: del intake_session.conversation_history (último del assistant)
        # - assessment/training/nutrition/progress: resumen del agente
        # - completed: mensaje de fin
        
        # Si current_phase == "onboarding", extrae la pregunta actual del IntakeSession
        # (el IntakeAgent expone esto vía intake_session.questionnaire + next_question_id)
        
        # Determina needs_user_input según current_phase
        # Determina expecting_images según el QuestionType de la pregunta actual
        ...
```

**3.3 Integración con factory.py**:

Modifica `cli/commands/factory.py` para que `Container` exponga:
- `container.workflow` (el grafo compilado, ya existente)
- `container.repos` (todos los repositorios, incluido `telegram_user`)
- `container.workflow_runner` (instancia de `WorkflowRunner`)

Mantén la firma actual de `build_container()` y SOLO añade campos. No rompas el CLI existente.

**Tests** (`tests/test_telegram_bot/test_workflow_runner.py`):
- Mock del workflow LangGraph
- Test de invoke con `WorkflowInput` de onboarding → devuelve `WorkflowOutput` con `needs_user_input=True` y `current_question` poblada
- Test de invoke con checkin_data → devuelve archivo generado y `is_complete=True`
- Test de continuidad: dos invokes consecutivos para el mismo user_id comparten thread_id
- Test de aislamiento: dos user_ids distintos NO comparten estado

---

### PASO 4: Handler `/start` y flujo de onboarding (una pregunta/turno)

**4.1 Handler raíz** (`handlers/start.py`):

```python
@require_whitelist
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start
    
    Si el usuario es nuevo: registra y arranca el intake.
    Si ya está registrado: muestra estado actual.
    """
    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    runner = context.bot_data["container"].workflow_runner
    
    user_id = await user_mapping.resolve_user_id(chat_id)
    
    # ¿Tiene perfil ya?
    profile_repo = context.bot_data["container"].repos.user_profile
    existing = profile_repo.get(user_id)
    
    if existing:
        await update.message.reply_text(
            messages.welcome_back(existing.personal.name),
            parse_mode="HTML",
        )
        await _show_status(update, context, user_id)
        return
    
    # Onboarding nuevo
    await update.message.reply_text(messages.onboarding_intro(), parse_mode="HTML")
    
    # Primera invocación del workflow → primera pregunta
    output = await runner.invoke(WorkflowInput(user_id=user_id, phase_hint="onboarding"))
    await _send_workflow_output(update, context, output, user_id)
```

**4.2 Flujo de intake — una pregunta por turno** (`handlers/intake_flow.py`):

El IntakeAgent del proyecto YA está diseñado conversacionalmente (turno por turno). El handler de Telegram simplemente traduce: recibe la respuesta del usuario, la pasa al workflow, recibe la siguiente pregunta, la envía.

**Patrón**:

```python
async def handle_intake_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler general para mensajes durante el onboarding.
    Se registra con filtro para que solo capture cuando current_phase == "onboarding".
    """
    chat_id = update.effective_chat.id
    user_id = await context.bot_data["user_mapping"].resolve_user_id(chat_id)
    runner = context.bot_data["container"].workflow_runner
    
    # Detectar tipo de mensaje
    if update.message and update.message.photo:
        # Foto subida
        photo_paths = await _download_photos(update, context, user_id)
        input = WorkflowInput(user_id=user_id, image_paths=photo_paths)
    elif update.callback_query:
        # Botón inline pulsado
        await update.callback_query.answer()
        # callback_data formato: "intake:value" → extraemos value
        value = update.callback_query.data.split(":", 1)[1]
        input = WorkflowInput(user_id=user_id, user_message=value)
    else:
        # Texto libre
        input = WorkflowInput(user_id=user_id, user_message=update.message.text)
    
    # Ejecutar workflow
    async with _typing_indicator(context, chat_id):
        output = await runner.invoke(input)
    
    await _send_workflow_output(update, context, output, user_id)
```

Cada turno es:
1. Usuario manda texto / pulsa botón / sube foto
2. Handler construye WorkflowInput
3. Workflow procesa, IntakeAgent valida la respuesta y genera la siguiente pregunta
4. Handler envía la nueva pregunta (con botones si aplica)
5. Vuelta al paso 1

**4.3 Botones inline según tipo de pregunta** (`keyboards/question_keyboard.py`):

El IntakeSession expone la pregunta actual. Según `QuestionType`, generamos teclado:

```python
def keyboard_for_question(question: Question) -> InlineKeyboardMarkup | None:
    """
    Devuelve teclado inline si la pregunta es cerrada con opciones.
    Para texto libre, retorna None (el usuario teclea normal).
    
    Formato callback_data: "intake:{value}" para que el handler de intake_flow
    lo procese correctamente.
    """
    if question.question_type == QuestionType.YES_NO:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Sí", callback_data="intake:yes"),
            InlineKeyboardButton("No", callback_data="intake:no"),
        ]])
    
    if question.question_type == QuestionType.SELECT:
        # Una opción por fila para mejor lectura en móvil
        buttons = [
            [InlineKeyboardButton(opt, callback_data=f"intake:{opt}")]
            for opt in question.options
        ]
        return InlineKeyboardMarkup(buttons)
    
    if question.question_type == QuestionType.SCALE:
        # Escala 1-10 en dos filas
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(str(i), callback_data=f"intake:{i}") for i in range(1, 6)],
            [InlineKeyboardButton(str(i), callback_data=f"intake:{i}") for i in range(6, 11)],
        ])
    
    if question.question_type == QuestionType.MULTI_SELECT:
        # Multi-select es complejo en Telegram. Mejor pedir texto libre con instrucción:
        # "Escribe las opciones separadas por coma: A, B, C"
        # El agente parsea la respuesta. Retornamos None para que sea texto.
        return None
    
    # TEXT, NUMBER, TIME, IMAGE → sin teclado, el usuario escribe o adjunta foto
    return None
```

Para `MULTI_SELECT`, en lugar de teclado, el mensaje incluye las opciones en el texto y pide separarlas con coma. Esto es más simple que gestionar selecciones múltiples con estado intermedio.

**4.4 Manejo de fotos** (`services/photo_storage.py`):

```python
class PhotoStorageService:
    """Descarga fotos de Telegram y las guarda en disco."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        base_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_photo(
        self,
        bot: Bot,
        photo_file_id: str,
        user_id: str,
        category: Literal["body", "gym", "checkin"],
    ) -> Path:
        """
        Descarga la foto y la guarda en {base_dir}/{user_id}/{category}/{timestamp}.jpg
        Retorna el path local.
        """
        ...
```

Las fotos van a `data/photos/{user_id}/{category}/`. El `image_paths` que recibe el workflow es la lista de paths locales.

Cuando la pregunta actual es de tipo IMAGE y el usuario manda una foto, se guarda y se pasa al workflow.

**4.5 Indicador de typing**:

```python
@asynccontextmanager
async def _typing_indicator(context, chat_id):
    """Context manager que mantiene 'escribiendo...' mientras se procesa."""
    stop = asyncio.Event()
    
    async def keep_typing():
        while not stop.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    
    task = asyncio.create_task(keep_typing())
    try:
        yield
    finally:
        stop.set()
        await task
```

Esencial porque las llamadas a Claude pueden tardar varios segundos y el usuario necesita feedback visual.

**4.6 Envío de output al usuario**:

```python
async def _send_workflow_output(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    output: WorkflowOutput,
    user_id: str,
):
    """Traduce WorkflowOutput a mensajes/archivos de Telegram."""
    chat_id = update.effective_chat.id
    
    # 1. Errores y warnings
    if output.errors:
        await context.bot.send_message(
            chat_id=chat_id,
            text=messages.error_block(output.errors),
            parse_mode="HTML",
        )
    
    # 2. Mensaje del assistant + teclado si hay pregunta cerrada
    if output.assistant_message:
        keyboard = None
        if output.current_question:
            keyboard = keyboard_for_question(output.current_question)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=output.assistant_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    
    # 3. Archivos generados
    for file_path in output.generated_files:
        await _send_document(context.bot, chat_id, file_path)
    
    # 4. Si is_complete y hay next_checkin_date: programar recordatorio
    if output.is_complete and output.next_checkin_date:
        scheduler = context.bot_data["scheduler"]
        scheduler.schedule_checkin_reminder(user_id, chat_id, output.next_checkin_date)
```

**Tests** (`tests/test_telegram_bot/test_intake_flow.py`):
- Mock de Update con texto → input correcto al runner
- Mock de Update con callback_query "intake:M" → input con user_message="M"
- Mock de Update con foto → fotos descargadas y paths en input
- Output con pregunta YES_NO → mensaje con teclado de 2 botones
- Output con pregunta TEXT → mensaje sin teclado
- Output con pregunta SCALE → mensaje con teclado de 10 botones en 2 filas
- Output con generated_files → documentos enviados
- Output con is_complete=True y next_checkin_date → scheduler.schedule_checkin_reminder llamado

---

### PASO 5: Handler `/checkin` y flujo de check-in

El check-in NO es del IntakeAgent. Es un flujo separado donde la UI recopila los datos del `CheckinInput` y los pasa al workflow de una sola vez.

**5.1 Handler raíz** (`handlers/checkin.py`):

```python
@require_whitelist
async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /checkin
    
    Inicia el check-in bisemanal. Recopila peso, medidas, fotos opcionales,
    feedback subjetivo, y notas.
    """
    chat_id = update.effective_chat.id
    user_id = await context.bot_data["user_mapping"].resolve_user_id(chat_id)
    
    # Validar que el usuario tiene mesociclo activo
    mesocycle = context.bot_data["container"].repos.mesocycle.get_current(user_id)
    if not mesocycle:
        await update.message.reply_text(messages.no_active_mesocycle())
        return
    
    # Iniciar flujo de recogida de datos
    context.user_data["checkin_in_progress"] = True
    context.user_data["checkin_data"] = _empty_checkin_data()
    context.user_data["checkin_step"] = "weights"
    
    await update.message.reply_text(messages.checkin_intro(mesocycle), parse_mode="HTML")
    await _ask_next_checkin_field(update, context)
```

**5.2 Flujo de recogida secuencial** (`handlers/checkin_flow.py`):

El check-in tiene pasos fijos. Cada uno pide un campo. Usa `context.user_data["checkin_step"]` como state machine:

1. **`weights`** — pide 3-5 pesos en ayunas separados por coma
2. **`measurements`** — pregunta una a una: cintura, cadera, brazo, etc. (cada una con botón "Saltar")
3. **`photos`** — pide subir 4 fotos en el mismo formato que el onboarding (botón "Sin fotos esta vez")
4. **`adherence`** — escala 1-10 con botones
5. **`cheat_meals`** — botones 0/1/2/3+
6. **`steps`** — texto numérico para pasos diarios promedio
7. **`subjective`** — 7 escalas 1-10 con botones secuenciales (energía, sueño, hambre, motivación, estrés, DOMS, ánimo)
8. **`pain`** — sí/no con botones; si sí: pide descripción en texto
9. **`training_logs`** — opcional, botón "Adjuntar después" o texto libre
10. **`notes`** — texto libre opcional (botón "Sin notas")

Cada paso: 
- Lee la respuesta del usuario
- Valida
- Guarda en `context.user_data["checkin_data"]`
- Avanza `checkin_step` al siguiente
- Llama a `_ask_next_checkin_field`

```python
async def handle_checkin_message(update, context):
    """Procesa mensaje durante el check-in."""
    if not context.user_data.get("checkin_in_progress"):
        return  # no estamos en check-in, ignorar
    
    step = context.user_data["checkin_step"]
    handler = _CHECKIN_STEP_HANDLERS[step]
    
    try:
        await handler(update, context)
    except ValueError as e:
        await update.effective_message.reply_text(f"⚠️ {e}\n\nVuelve a intentarlo.")
        return
    
    # Avanzar al siguiente paso
    context.user_data["checkin_step"] = _next_step(step)
    await _ask_next_checkin_field(update, context)
```

**5.3 Finalización**:

Cuando el último paso (`notes`) se completa, se construye el `CheckinInput` final y se invoca el workflow:

```python
async def _finalize_checkin(update, context):
    """Construye CheckinInput y ejecuta el workflow."""
    data = context.user_data["checkin_data"]
    user_id = await context.bot_data["user_mapping"].resolve_user_id(update.effective_chat.id)
    
    checkin_input = _build_checkin_input(data)
    runner = context.bot_data["container"].workflow_runner
    
    await update.effective_message.reply_text(
        "Procesando tu check-in... Esto puede tardar 30-60 segundos.",
        parse_mode="HTML",
    )
    
    async with _typing_indicator(context, update.effective_chat.id):
        output = await runner.invoke(WorkflowInput(
            user_id=user_id,
            phase_hint="checkin",
            checkin_data=checkin_input,
            image_paths=data["photos"],
        ))
    
    # Limpiar estado del flujo
    context.user_data["checkin_in_progress"] = False
    context.user_data["checkin_data"] = None
    context.user_data["checkin_step"] = None
    
    # Enviar resultado (PDF + resumen + decisión del coach)
    await _send_workflow_output(update, context, output, user_id)
```

**Tests** (`tests/test_telegram_bot/test_checkin_flow.py`):
- Flujo completo simulado: cada paso pide siguiente campo
- Validación: peso < 30 o > 250 kg → pide reintroducir
- Construcción de CheckinInput correcta desde user_data
- Sin mesociclo activo → mensaje de error
- Salto opcional en medidas: el campo queda None y avanza

---

### PASO 6: Handlers auxiliares

**6.1 `/status`** (`handlers/status.py`):

Muestra:
- Nombre del usuario
- Mesociclo activo (nombre, microciclo actual, fecha inicio)
- Próximo check-in
- Últimos archivos generados (con botones para reenviar)

Formato HTML:

```
<b>Estado de Luis</b>
━━━━━━━━━━━━━

📋 <b>Mesociclo activo</b>
Hipertrofia Upper/Lower
Microciclo 2 de 5 (1 mayo - 14 mayo)

📅 <b>Próximo check-in</b>
29 mayo (en 14 días)

📂 <b>Archivos recientes</b>
• Mesociclo_Luis_2026-05-15.xlsx
• Plan_Nutricional_Luis_2026-05-15.pdf
```

Botones inline: "Reenviar mesociclo", "Reenviar dieta", "Hacer check-in ahora".

**6.2 `/export`** (`handlers/export.py`):

Submenú con botones inline:
- Mesociclo
- Plan nutricional
- Último informe de progreso

Cada opción regenera el archivo (llamando al generador directamente con el modelo del repo, NO ejecutando el agente) y lo envía.

**6.3 `/help`** (`handlers/help.py`):

Mensaje estático con descripción de comandos.

**6.4 Comando fallback**:

Si el usuario manda algo fuera de un flujo activo y no coincide con un comando, responde:
"No entiendo. Prueba /help para ver los comandos disponibles."

---

### PASO 7: Scheduler de recordatorio de check-in (único tipo)

**7.1 Servicio** (`services/scheduler.py`):

Solo gestiona UN tipo de notificación: el recordatorio bisemanal de check-in. Nada más.

```python
class CheckinReminderScheduler:
    """
    Programa y dispara el recordatorio de check-in usando el JobQueue
    de python-telegram-bot (basado en APScheduler).
    
    Solo gestiona este tipo de notificación. No hay recordatorios diarios
    ni de otra naturaleza.
    """
    
    def __init__(self, job_queue: JobQueue, repos: Repositories):
        self.job_queue = job_queue
        self.repos = repos
    
    def schedule_checkin_reminder(
        self,
        user_id: str,
        chat_id: int,
        checkin_date: date,
    ):
        """
        Programa un job único que mande mensaje en checkin_date a las 10:00.
        Si ya existe un job para este user_id, lo reemplaza.
        """
        run_at = datetime.combine(checkin_date, time(10, 0))
        job_name = f"checkin_reminder_{user_id}"
        
        # Cancelar job previo si existe
        for job in self.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        
        self.job_queue.run_once(
            self._send_reminder,
            when=run_at,
            chat_id=chat_id,
            name=job_name,
            data={"user_id": user_id},
        )
    
    async def _send_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Callback que envía el recordatorio."""
        chat_id = context.job.chat_id
        user_id = context.job.data["user_id"]
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=messages.checkin_reminder(),
            parse_mode="HTML",
        )
    
    async def restore_scheduled_reminders(self):
        """
        Al arrancar el bot, lee próximos check-ins de los repos y reprograma
        recordatorios pendientes. El JobQueue NO persiste entre reinicios.
        
        Recorre todos los chat_ids registrados, busca su user_id, obtiene el
        último ProgressLog (o el assessment inicial si no hay logs) para saber
        next_checkin_date, y reprograma.
        """
        ...
```

**7.2 Integración**:

En `app.py`, después de inicializar:

```python
async def post_init(application):
    # ... existente ...
    scheduler = CheckinReminderScheduler(
        application.job_queue,
        container.repos,
    )
    application.bot_data["scheduler"] = scheduler
    await scheduler.restore_scheduled_reminders()
```

**Tests** (`tests/test_telegram_bot/test_scheduler.py`):
- Mock de JobQueue → schedule_checkin_reminder llama a run_once con args correctos
- Reprogramar mismo user_id → cancela el anterior antes
- restore_scheduled_reminders carga próximos checkins de los repos para todos los usuarios registrados
- _send_reminder envía mensaje con texto correcto

---

### PASO 8: App principal y arranque

**8.1 `src/telegram_bot/app.py`**:

```python
import logging
from typing import Final

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from src.config.settings import build_settings
from cli.commands.factory import build_container
from src.telegram_bot.handlers import (
    start, checkin, status, export, help as help_cmd,
    intake_flow, checkin_flow,
)
from src.telegram_bot.services.scheduler import CheckinReminderScheduler
from src.telegram_bot.services.user_mapping import UserMappingService

_logger: Final[logging.Logger] = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Inicializa dependencias."""
    settings = build_settings()
    container = build_container(settings)
    
    application.bot_data["settings"] = settings
    application.bot_data["container"] = container
    application.bot_data["user_mapping"] = UserMappingService(
        container.repos.telegram_user, settings
    )
    
    scheduler = CheckinReminderScheduler(application.job_queue, container.repos)
    application.bot_data["scheduler"] = scheduler
    await scheduler.restore_scheduled_reminders()
    
    _logger.info("Bot inicializado. Whitelist: %s", settings.allowed_chat_ids)


def build_application() -> Application:
    """Construye la Application con todos los handlers registrados."""
    settings = build_settings()
    
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    
    # Commands
    app.add_handler(CommandHandler("start", start.start_command))
    app.add_handler(CommandHandler("checkin", checkin.checkin_command))
    app.add_handler(CommandHandler("status", status.status_command))
    app.add_handler(CommandHandler("export", export.export_command))
    app.add_handler(CommandHandler("help", help_cmd.help_command))
    
    # Callback queries (botones inline) — patrones por prefijo
    app.add_handler(CallbackQueryHandler(intake_flow.handle_callback, pattern="^intake:"))
    app.add_handler(CallbackQueryHandler(checkin_flow.handle_callback, pattern="^checkin:"))
    app.add_handler(CallbackQueryHandler(export.handle_callback, pattern="^export:"))
    
    # Mensajes:
    # - Fotos: van a intake o checkin según el flujo activo
    # - Texto: idem
    # El handler interno verifica context.user_data para saber en qué flujo está
    app.add_handler(MessageHandler(filters.PHOTO, _route_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _route_text))
    
    # Error handler global
    app.add_error_handler(_global_error_handler)
    
    return app


async def _route_photo(update, context):
    """Decide si la foto va a intake o checkin según el flujo activo."""
    if context.user_data.get("checkin_in_progress"):
        await checkin_flow.handle_photo(update, context)
    else:
        await intake_flow.handle_photo(update, context)


async def _route_text(update, context):
    """Decide si el texto va a intake o checkin según el flujo activo."""
    if context.user_data.get("checkin_in_progress"):
        await checkin_flow.handle_text(update, context)
    else:
        await intake_flow.handle_text(update, context)


async def _global_error_handler(update, context):
    """Loggea el error y notifica al admin."""
    _logger.exception("Error procesando update", exc_info=context.error)
    admin_id = context.bot_data["settings"].telegram_admin_chat_id
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=f"<b>Error en bot</b>\n<pre>{context.error}</pre>",
                parse_mode="HTML",
            )
        except Exception:
            _logger.exception("No se pudo notificar al admin")


def run_bot():
    """Punto de entrada llamado desde la CLI."""
    logging.basicConfig(level=logging.INFO)
    app = build_application()
    _logger.info("Bot arrancando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
```

**8.2 Patrón de prefijos en callback_data**:

Para diferenciar callbacks:
- `intake:{value}` (ej: `intake:M`, `intake:yes`, `intake:7`)
- `checkin:{field}:{value}` (ej: `checkin:adherence:8`)
- `export:{type}` (ej: `export:mesocycle`)

Esto evita que un callback de export sea procesado por intake_flow.

**Tests** (`tests/test_telegram_bot/test_app.py`):
- build_application registra los handlers esperados
- _route_photo va a checkin si checkin_in_progress
- _route_photo va a intake si no
- _global_error_handler manda mensaje a admin con HTML correcto

---

### PASO 9: Mensajes en español

Crea plantillas de texto en `src/telegram_bot/messages/`:

`intake.py`:
```python
def welcome_back(name: str) -> str:
    return f"¡Hola, <b>{name}</b>! 👋\n\nUsa /status para ver tu estado actual."

def onboarding_intro() -> str:
    return (
        "<b>Bienvenido a tu coach personal</b>\n\n"
        "Te voy a hacer algunas preguntas para conocerte y crear tu plan "
        "de entrenamiento y nutrición personalizado.\n\n"
        "Iremos una pregunta a la vez. Puedes parar cuando quieras y "
        "retomar después con /start. Tardarás unos 10-15 minutos en total."
    )

# ... resto
```

`checkin.py`, `status.py`, `errors.py` igual.

**Reglas de estilo**:
- HTML para formatear (Telegram lo acepta nativo): `<b>`, `<i>`, `<code>`, `<pre>`
- Emojis sutiles: 1 por mensaje máximo, siempre relevante (📋 📅 💪 ✅ ⚠️)
- Líneas cortas, separadas en bloques con `\n\n`
- Tuteo, registro cercano pero profesional
- No usar Markdown (parse_mode HTML es más robusto en Telegram)

---

### PASO 10: Documentación y arranque

**10.1 `README.md`** — añade sección "Bot de Telegram":

```markdown
## Bot de Telegram

Además del CLI, el sistema expone una interfaz por bot de Telegram.

### Setup

1. Crea un bot con [@BotFather](https://t.me/botfather) y copia el token.
2. Obtén los chat_ids de los usuarios autorizados (cada uno escribe a [@userinfobot](https://t.me/userinfobot)).
3. Añade a `.env`:
   ```
   TELEGRAM_BOT_TOKEN=tu_token_aqui
   TELEGRAM_ALLOWED_CHAT_IDS=chat_id_1,chat_id_2,chat_id_3
   TELEGRAM_ADMIN_CHAT_ID=tu_chat_id
   ```
4. Arranca el bot:
   ```bash
   uv run fitness telegram
   ```

### Comandos

- `/start` — Inicia onboarding o muestra estado
- `/checkin` — Check-in bisemanal
- `/status` — Estado actual del plan
- `/export` — Reenvía archivos (mesociclo, dieta, progreso)
- `/help` — Ayuda
```

**10.2 Actualiza `handoff.md`**:

Añade sección 13 "Interfaz Telegram" con:
- Estructura `src/telegram_bot/`
- Comandos disponibles
- Variables de entorno
- Marca el proyecto como "Funcional end-to-end por CLI y Telegram"

---

## REQUISITOS GENERALES

- Type hints completos
- Docstrings en español
- `logging` stdlib (NO loguru — handoff.md punto 10)
- ruff solo sobre lo que tocas
- Async en todos los handlers (python-telegram-bot 21+ es async nativo)
- Tests con pytest-asyncio
- Reutilizar `build_container()` y `persist_artifacts()` — NO duplicar lógica de los agentes
- NO modificar agentes, generadores, ni grafo. Si necesitas algo de un agente que no existe, dímelo en vez de implementarlo en el bot.

## CHECKPOINT FINAL

Tras el paso 10:

```bash
uv run fitness telegram
# Bot escuchando

# En Telegram (varios usuarios pueden usarlo en paralelo, cada uno con su estado):
/start
# → cuestionario conversacional, una pregunta a la vez
# → preguntas cerradas con botones, preguntas abiertas con texto
# → sube fotos cuando pida
# → al final recibes Mesociclo.xlsx + Plan_Nutricional.pdf
# → recordatorio único programado para 14 días después

/status
# → muestra mesociclo activo, próximo check-in, archivos

/checkin
# → flujo guiado paso a paso para recopilar CheckinInput
# → recibes Informe_Progreso.pdf con la decisión del coach
# → siguiente recordatorio reprogramado a +14 días
```

Tests pasando (objetivo: añadir ~30-40 tests más al total existente). Cobertura de los handlers principales, runner, scheduler y mapping.

---

## ORDEN DE EJECUCIÓN

1. Antes de empezar, REVISA `handoff.md` completo y los siguientes archivos para confirmar firmas reales:
   - `src/graph/state.py` (FitnessState)
   - `src/graph/workflow.py` (entry points)
   - `cli/commands/factory.py` (build_container, persist_artifacts)
   - `src/db/repositories.py` (patrones de repositorio)
   - `src/agents/intake.py` (cómo expone la pregunta actual del IntakeSession)
   - `src/models/intake_session.py` o donde viva el modelo IntakeSession/Question

2. Si algo del prompt no encaja con el código real, dímelo ANTES de implementar y nos adaptamos.

3. Empieza por el PASO 1 (dependencias y settings). Espera mi confirmación antes de seguir.
````
