# GUÍA DE CONTEXTO DEL PROYECTO (para modelos de IA)

> Este documento da a un modelo de IA el **contexto real** del proyecto:
> qué es, cómo está estructurado, cómo fluyen los datos y qué
> convenciones seguir. Es la fuente de verdad junto con `CLAUDE.md`.
> Si un `prompt_*_vscode.md` (andamiaje escrito antes de implementar)
> contradice esta guía o el código, **gana el código**. Verifica siempre
> contra `src/models/` y `src/graph/state.py` antes de implementar.
>
> Última actualización: 2026-05-15. Tests: **215 pasando**.

## 1. Qué es

Sistema multi-agente en Python que actúa como nutricionista y entrenador
personal. Convierte un cuestionario y datos del usuario en salidas
accionables: evaluación corporal, mesociclo de entrenamiento (Excel),
plan nutricional (PDF) y seguimiento de progreso bisemanal (PDF). Usa una
base de conocimiento RAG (divulgadores de evidencia + estudios) para dar
contexto a los agentes. Funciona end-to-end por CLI.

## 2. Stack

Python 3.12+ · uv · LangGraph (checkpointer SQLite) · ChromaDB ·
Claude API (Anthropic) · SQLite · openpyxl · reportlab + matplotlib +
pillow · Typer + Rich · pytest · ruff (line-length 100). Pydantic v2
para todos los modelos de datos.

## 3. Flujo de datos (pipeline)

```
Cuestionario ─▶ IntakeAgent ─▶ UserProfile
                                   │
                                   ▼
                          AssessmentAgent ─▶ BodyAssessment
                                   │
                          ┌────────┴────────┐
                          ▼                 ▼
                  TrainingAgent       NutritionAgent
                  ─▶ Mesocycle        ─▶ NutritionPlan
                          │                 │
                          ▼                 ▼
                  Excel mesociclo    PDF plan nutricional
                          │
            (período activo de ~2 semanas)
                          │
                          ▼
        CheckinInput ─▶ ProgressAgent ─▶ ProgressLog ─▶ PDF informe
                          │
                  decisión del coach: continuar / ajustar
                  calorías / ajustar volumen / nuevo mesociclo
```

El orquestador LangGraph dirige este flujo según `current_phase`. La CLI
ejecuta el bucle externo (intake es conversacional, un turno por
`ainvoke()`).

## 4. Estructura y responsabilidades

```text
src/knowledge/   RAG: chunker, embeddings, indexer, retriever,
                 registry_sync, sources, video_ingest (yt-dlp + whisper)
src/models/      Modelos Pydantic del dominio (ver §5)
src/agents/      Agentes: intake, assessment, training, nutrition,
                 progress + base + claude_client (async, structured
                 outputs, reintentos, timeout)
src/graph/       state (FitnessState), workflow (nodos+routers),
                 checkpoints (SQLite)
src/generators/  MesocycleExcelGenerator, NutritionPDFGenerator,
                 ProgressPDFGenerator + styles/
src/db/          connection + repositories (uno por modelo persistido)
src/config/      settings (Pydantic settings; ANTHROPIC_API_KEY,
                 CHROMA_PERSIST_DIR, etc.)
src/tools/       VACÍO (solo __init__.py) — sin implementar
cli/             fitness_cli, knowledge_cli, commands/
tests/           Suite por módulo, con conftest de fixtures
output/          Archivos generados (xlsx/pdf)
```

## 5. Modelos de datos clave (campos reales)

Verifica estos campos antes de escribir código que los consuma; los
prompts de andamiaje a menudo asumen otros nombres.

- **UserProfile**: `id`, `personal` (`PersonalData`: `name`, `age`,
  `sex`, `height_cm`, `weight_kg`, …), `activity`, `nutrition`, `goals`,
  `gym`, `body_photo_paths`.
- **Mesocycle**: `id`, `user_id`, `name`, `start_date`, `phase`,
  `split_type`, `training_days_per_week`, `microcycles[Microcycle]`,
  `weekly_schedule`, `progression_strategy`, `notes?`. La **descarga**
  es un `Microcycle` con `is_deload=True`, no una entidad aparte. El
  programa canónico = `microcycles[0].training_days`.
  - `Microcycle`: `number`, `duration_days`, `is_deload`,
    `volume_modifier`, `training_days[TrainingDay]`.
  - `TrainingDay`: `day_number`, `day_label`, `is_rest_day`,
    `exercises[ProgrammedExercise]`, `target_steps`.
  - `ProgrammedExercise`: `order`, `exercise_id`, `exercise_name`
    (ya con indicaciones técnicas), `set_scheme`, `progression_notes?`.
    **No** existe `technique_notes`.
  - `SetScheme`: `total_sets`, `rep_range`, `rir`, `technique?`,
    `rest_seconds`, `description`. El descanso vive aquí.
  - `WeeklySchedule.days`: lista de dicts `{"day","type","steps"}`
    (`type` ∈ "pesas"/"descanso").
- **NutritionPlan**: `id`, `user_id`, `name`, `objective`, `phase`,
  `duration`, `start_date`, `training_day_diet`, `rest_day_diet`,
  `interchange_rules`, `cheat_meal_protocol?` (opcional),
  `general_tips`, `neat_cardio_notes`. **No** guarda esquema semanal.
  - `DailyDiet`: `day_type`, `macros` (`MacroDistribution`),
    `meals[Meal]`, `supplements[str]` (los suplementos viven aquí).
  - `MacroDistribution`: `calories/protein_g/carbs_g/fat_g` son `int`;
    `fiber_g?`.
- **ProgressLog**: `weight` (`WeightLog`), `measurements`
  (`BodyMeasurements`), `training` (`TrainingProgress`), `nutrition`
  (`NutritionAdherence`), `subjective` (`SubjectiveFeedback`),
  `photos?`, `daily_steps_avg`, `decision` (`ProgressDecision`),
  `report_summary`.
  - `TrainingProgress.exercises_progressed/stagnated/regressed` son
    **contadores `int`**, no listas. Las listas son `notable_prs` y
    `problem_exercises`.
  - `WeightLog.trend` ∈ {`losing`,`stable`,`gaining`}.
  - `ProgressDecision.action` enum: `continue`, `adjust_calories`,
    `adjust_macros`, `adjust_volume`, `early_deload`, `change_phase`,
    `new_mesocycle`.

## 6. Grafo LangGraph

- `FitnessState` (TypedDict, `total=False`) en `src/graph/state.py`.
  Claves relevantes: `current_phase`, `user_profile`, `body_assessment`,
  `current_mesocycle`, `current_nutrition_plan`, `progress_logs`,
  `generated_files`, `errors`, `warnings`. Los nodos devuelven dicts
  parciales; LangGraph hace merge.
- Nodos: intake, assessment, training, nutrition, progress,
  schedule_checkin, advance_microcycle. Routers condicionales por
  `current_phase` y por la decisión del último `ProgressLog`.
- Los nodos training/nutrition/progress, tras correr el agente,
  **generan el archivo** y añaden su path a `generated_files`
  (best-effort: si falla, va a `warnings` y el flujo continúa).
- `generated_files` vive en el **estado del grafo**, no en SQLite.

## 7. Generadores (`src/generators/`)

- Base `FileGenerator` (ABC) con `_build_filename` →
  `{Tipo}_{Nombre}_{fecha}.{ext}` en `output/`.
- `MesocycleExcelGenerator`: 3 hojas (Mesociclo con columna por
  microciclo y celdas vacías para rellenar en el gym, Esquema semanal,
  Notas y técnicas). Estructura canónica = `microcycles[0]`.
- `NutritionPDFGenerator`: portada, dieta entreno, dieta descanso,
  comparativa entreno/descanso (sustituye al "esquema semanal" porque
  el modelo no lo guarda), protocolo cheat (si existe), tips e
  intercambiabilidad, NEAT/cardio.
- `ProgressPDFGenerator`: 6 páginas; gráfica de peso matplotlib si hay
  `previous_logs` (≥2 puntos), si no texto.
- `styles/`: `colors.py` (paleta + helpers `argb`/`microcycle_color`),
  `excel_styles.py`, `pdf_styles.py`.

## 8. CLI

```
fitness start    --user-id <id>     onboarding conversacional
fitness checkin  --user-id <id>     check-in bisemanal
fitness status   --user-id <id>     estado + archivos en output/
fitness export-mesocycle  --user-id <id>
fitness export-nutrition  --user-id <id>
fitness export-progress   --user-id <id> [--log-id <id>]

fitness-kb list | stats | index-all | index <id> | search "<q>"
            | ingest-video <url> | sync-registry --dry-run | …
```

`cli/commands/factory.py` → `build_container()` arma settings, agentes,
retriever y repos; `persist_artifacts(state, repos)` guarda en SQLite.

## 9. Persistencia (`src/db/`)

Un repositorio por modelo: `UserProfileRepository` (`get`/`save`),
`BodyAssessmentRepository` (`get_latest`/`save`),
`MesocycleRepository` (`get_current`/`save`/`list_history`),
`NutritionPlanRepository` (`get_current`/`save`),
`ProgressLogRepository` (`list_for_user`/`save`). SQLite local.

## 10. Convenciones (prevalecen sobre cualquier prompt)

- **Logging**: `logging` de stdlib,
  `_logger: Final[logging.Logger] = logging.getLogger(__name__)`.
  **No** loguru (no está instalado), aunque algún prompt lo pida.
- **ruff**: `format` + `check`, line-length 100. Ejecútalo **solo sobre
  los archivos/carpetas que tocas**, nunca sobre todo `src/ cli/ tests/`
  (reformatea archivos ajenos y ensucia el diff/commit).
- Docstrings y comentarios en **español**. Type hints obligatorios.
  Pydantic para datos. Sin `print()` (usa logging o Rich console).
- Async donde tenga sentido (API/I-O). Clases con responsabilidad única.
- Tests en `tests/test_<modulo>/` con `conftest.py` de fixtures. pytest,
  `asyncio_mode=auto`. `ANTHROPIC_API_KEY` se mockea en conftest.
- Cambios quirúrgicos: cada línea cambiada traza a la petición. No
  refactorizar lo que no se pidió. Mínimo código necesario.

## 11. Cómo ejecutar y testear

```bash
uv sync --extra dev
cp .env.example .env          # ANTHROPIC_API_KEY=...
uv run pytest                 # 215 tests
uv run ruff check <ruta>      # solo lo que tocas
uv run fitness start --user-id usuario1
```

## 12. Estado actual y siguiente fase

Funcional end-to-end por CLI. **Pendiente**: interfaz para usuarios no
técnicos (bot de Telegram o web app) y herramientas de agente
(`src/tools/`, hoy vacío). Mantén este archivo actualizado cuando el
estado del proyecto cambie.
