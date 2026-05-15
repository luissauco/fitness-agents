# fitness-agents

[English](README.en.md) | Espanol

[![CI](https://github.com/luissauco/fitness-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/luissauco/fitness-agents/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![RAG](https://img.shields.io/badge/RAG-ChromaDB-purple)

Sistema multi-agente para crear planes de entrenamiento y nutricion con RAG, modelos Pydantic y una base de conocimiento fitness en espanol.

El objetivo es convertir evidencia, divulgacion tecnica y datos del usuario en salidas accionables: cuestionarios, evaluaciones, mesociclos, planes nutricionales y seguimiento de progreso.

## Por Que Existe

La mayoria de herramientas fitness con IA responden de forma generica. `fitness-agents` busca ser mas trazable y estructurado:

- Recupera contexto desde una base de conocimiento local antes de responder.
- Modela datos de usuario, ejercicios, nutricion, mesociclos y progreso con Pydantic.
- Valida coherencia entre entrenamiento, nutricion, equipamiento y objetivos.
- Esta pensado para trabajar en espanol y con contenido de hipertrofia basado en biomecanica, volumen, intensidad, fatiga y seleccion de ejercicios.

## Estado Actual

Ya implementado:

- CLI `fitness-kb` para listar, ingerir, indexar y buscar fuentes.
- CLI `fitness` con comandos `start`, `checkin`, `status` y `export-mesocycle`, `export-nutrition`, `export-progress`.
- Base RAG con ChromaDB, chunking, embeddings y filtros por topic, autor, fiabilidad y tipo de fuente.
- Ingesta de videos con `yt-dlp` y transcripcion local.
- Registry con cientos de transcripciones fitness en espanol.
- Modelos Pydantic para usuario, cuestionario, evaluacion corporal, ejercicios, mesociclo, nutricion, progreso, sesion de intake y check-in.
- Agentes especializados: intake, evaluacion corporal, entrenamiento, nutricion y progreso.
- `ClaudeClient` async con structured outputs, reintentos configurables y timeout.
- Orquestador LangGraph con checkpoints SQLite y estado compartido por sesion.
- Persistencia SQLite con repositorios para usuarios y sesiones.
- Generadores de archivos: Excel del mesociclo (programa, esquema semanal y notas), PDF del plan nutricional y PDF del informe de progreso con grafica de peso.
- Generacion cableada en el grafo (los nodos producen los archivos) y comandos CLI para regenerarlos sin re-ejecutar agentes.
- Prompts especificos por agente con contexto RAG.
- Suite de tests para agentes, base de datos, grafo y generadores.

En desarrollo:

- Interfaz para usuarios no tecnicos (bot de Telegram o web app).
- Herramientas de agente (`src/tools/`) aun sin implementar.
- Fuentes cientificas adicionales y citas normalizadas.

## Demo Rapida

```bash
uv sync --extra dev
cp .env.example .env

# Base de conocimiento
uv run fitness-kb list
uv run fitness-kb index-all
uv run fitness-kb search "como entrenar pectoral para hipertrofia" --agent training -k 3

# Sistema de agentes
uv run fitness start --user-id usuario1
uv run fitness checkin --user-id usuario1
uv run fitness status --user-id usuario1

# Regenerar archivos sin re-ejecutar agentes
uv run fitness export-mesocycle --user-id usuario1
uv run fitness export-nutrition --user-id usuario1
uv run fitness export-progress --user-id usuario1
```

Hay una guia mas completa en [docs/DEMO.md](docs/DEMO.md). English version: [docs/DEMO.en.md](docs/DEMO.en.md).

## Casos De Uso

- Construir un entrenador personal con agentes de IA.
- Crear una base de conocimiento fitness consultable por RAG.
- Generar estructuras validadas para planes de entrenamiento y nutricion.
- Experimentar con modelos Pydantic para productos fitness.
- Analizar contenido de divulgadores y convertirlo en fuentes indexables.

## Stack

- Python 3.12+
- uv
- ChromaDB
- sentence-transformers
- Pydantic v2
- Typer + Rich
- yt-dlp
- faster-whisper
- pytest + ruff
- LangGraph y Claude API para la fase de agentes

## Instalacion

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra dev

cp .env.example .env
```

Edita `.env` si vas a usar proveedores externos:

```bash
ANTHROPIC_API_KEY=...
```

## CLI

```bash
uv run fitness-kb list
uv run fitness-kb stats
uv run fitness-kb index-all
uv run fitness-kb index <source_id>
uv run fitness-kb search "<query>"
uv run fitness-kb search "<query>" --agent training -k 5
uv run fitness-kb ingest-video <url> --topics hypertrophy,biomechanics
uv run fitness-kb list-profile <profile_url> --output videos.txt
uv run fitness-kb ingest-from-list videos.txt --topics hypertrophy
uv run fitness-kb sync-registry --dry-run
```

## Bot de Telegram

Además del CLI, el sistema expone una interfaz conversacional por bot de Telegram.

### Setup

1. Crea un bot con [@BotFather](https://t.me/botfather) y copia el token.
2. Obtén los chat IDs de los usuarios autorizados (cada uno envía un mensaje a [@userinfobot](https://t.me/userinfobot)).
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

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| `/start` | Inicia el cuestionario de onboarding o muestra el estado actual |
| `/checkin` | Inicia el check-in bisemanal guiado |
| `/status` | Muestra mesociclo activo, próximo check-in y archivos generados |
| `/export` | Reenvía archivos generados (mesociclo Excel, dieta PDF, informe PDF) |
| `/help` | Muestra la ayuda con todos los comandos |

### Arquitectura

El bot es una capa de presentación pura. No duplica lógica de agentes: llama al mismo workflow LangGraph que usa el CLI y traduce el estado a mensajes de Telegram. Cada usuario autorizado tiene su propio estado aislado (thread_id = user_id en el checkpointer SQLite).

## Estructura

```text
cli/                    Interfaz de terminal fitness-kb
data/                   Datos estructurados auxiliares
docs/                   Demos y documentacion de producto
scripts/                Scripts operativos de ingesta/clasificacion
src/config/             Configuracion del proyecto
src/knowledge/          RAG, fuentes, registry, indexacion y recuperacion
src/models/             Modelos Pydantic del dominio fitness
src/agents/             Agentes especializados (intake, assessment, training, nutrition, progress)
src/generators/         Generadores XLSX/PDF (mesociclo, nutricion, progreso)
src/graph/              Orquestacion LangGraph con checkpoints SQLite
src/db/                 Persistencia SQLite (conexion y repositorios)
tests/                  Suite de tests
```

## Calidad

```bash
uv run ruff check .
uv run pytest
```

La suite cubre chunking, indexacion, recuperacion, sincronizacion del registry, modelos fitness, validadores, agentes, base de datos y grafo.

## Roadmap

El plan publico esta en [ROADMAP.md](ROADMAP.md). English version: [ROADMAP.en.md](ROADMAP.en.md). Las contribuciones mas utiles ahora mismo son:

- Mejorar ejemplos de uso.
- Anadir fuentes cientificas con metadata limpia.
- Crear casos de prueba para agentes.
- Construir la interfaz para usuarios no tecnicos (bot de Telegram o web app).
- Preparar una demo web o notebook reproducible.

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md) para configurar el entorno, ejecutar checks y proponer cambios. English version: [CONTRIBUTING.en.md](CONTRIBUTING.en.md). Las issues pequenas con etiqueta `good first issue` son especialmente bienvenidas.

## Topics Sugeridos En GitHub

`fitness`, `ai-agents`, `rag`, `langchain`, `pydantic`, `nutrition`, `workout-planner`, `personal-trainer`, `spanish`, `knowledge-base`

## Licencia

MIT. Ver [LICENSE](LICENSE).
