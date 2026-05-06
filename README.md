# fitness-agents

Sistema multi-agente de nutrición y entrenamiento personal basado en LangGraph y Claude.

## Visión general

Cinco agentes especializados (intake, evaluación corporal, entrenamiento, nutrición y progreso)
coordinados por un orquestador LangGraph. Todos consultan una base de conocimiento RAG
construida sobre el contenido de Fran Pérez Jurado (@franperezjurado) y estudios científicos
de referencia en hipertrofia y nutrición deportiva.

Salidas:
- Mesociclos de entrenamiento en Excel (divididos en microciclos semanales).
- Planes nutricionales en PDF.
- Seguimiento bisemanal con ajustes basados en progreso.

## Stack

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) como gestor de paquetes
- LangGraph (orquestación de agentes)
- ChromaDB (vector store local)
- Claude API (Anthropic)
- sentence-transformers (embeddings multilingües)
- Typer + Rich (CLI)
- pytest + ruff

## Estado actual

Construyendo el módulo RAG (`src/knowledge/`). El resto de módulos son stubs por ahora.

## Setup

```bash
# Instalar uv si no lo tienes
curl -LsSf https://astral.sh/uv/install.sh | sh

# Crear entorno e instalar dependencias
uv sync --extra dev

# Variables de entorno
cp .env.example .env
# Editar .env y añadir ANTHROPIC_API_KEY
```

## Estructura

```
src/
  knowledge/   ← módulo RAG (foco actual)
  agents/      ← agentes LangGraph (futuro)
  models/      ← modelos Pydantic (futuro)
  generators/  ← generadores xlsx/pdf (futuro)
  graph/       ← grafo de estados LangGraph (futuro)
  tools/       ← herramientas de agentes (futuro)
  db/          ← persistencia SQLite (futuro)
  config/      ← configuración
cli/           ← interfaz de terminal
tests/         ← tests
output/        ← archivos generados
```

## Uso del CLI (RAG)

Disponible una vez implementado el módulo:

```bash
fitness-kb index-all              # Indexa todo el registry
fitness-kb index <source_id>      # Indexa una fuente específica
fitness-kb search "<query>"       # Búsqueda rápida de prueba
fitness-kb stats                  # Estadísticas del índice
fitness-kb ingest-video <url>     # Descarga, transcribe e indexa un vídeo
fitness-kb list                   # Lista todas las fuentes registradas
```
