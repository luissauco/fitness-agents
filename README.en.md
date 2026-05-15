# fitness-agents

English | [Espanol](README.md)

[![CI](https://github.com/luissauco/fitness-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/luissauco/fitness-agents/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![RAG](https://img.shields.io/badge/RAG-ChromaDB-purple)

A multi-agent system for generating training and nutrition plans with RAG, Pydantic models, and a Spanish fitness knowledge base.

The goal is to turn evidence, technical fitness content, and user data into actionable outputs: questionnaires, assessments, mesocycles, nutrition plans, and progress reviews.

## Why It Exists

Most AI fitness tools answer in a generic way. `fitness-agents` is designed to be more traceable and structured:

- It retrieves local knowledge-base context before answering.
- It models users, exercises, nutrition, mesocycles, and progress with Pydantic.
- It validates consistency across training, nutrition, equipment, and goals.
- It is built for Spanish-first hypertrophy content around biomechanics, volume, intensity, fatigue, and exercise selection.

## Current Status

Implemented:

- `fitness-kb` CLI for listing, ingesting, indexing, and searching sources.
- `fitness` CLI with `start`, `checkin`, `status`, and `export-mesocycle`, `export-nutrition`, `export-progress` commands.
- RAG layer with ChromaDB, chunking, embeddings, and filters by topic, author, reliability, and source type.
- Video ingestion with `yt-dlp` and local transcription.
- Registry with hundreds of Spanish fitness transcripts.
- Pydantic models for users, questionnaires, body assessment, exercises, mesocycles, nutrition, progress, intake sessions, and check-ins.
- Specialized agents: intake, body assessment, training, nutrition, and progress.
- Async `ClaudeClient` with structured outputs, configurable retries, and timeout.
- LangGraph orchestrator with SQLite checkpoints and per-session shared state.
- SQLite persistence with repositories for users and sessions.
- File generators: mesocycle Excel (program, weekly schedule, notes), nutrition plan PDF, and progress report PDF with a weight chart.
- Generation wired into the graph (nodes produce the files) plus CLI commands to regenerate them without re-running agents.
- Per-agent prompts with RAG context.
- Test suite covering agents, database, graph, and generators.

In progress:

- Non-technical user interface (Telegram bot or web app).
- Agent tools (`src/tools/`) not implemented yet.
- Additional scientific sources with normalized citations.

## Quick Demo

```bash
uv sync --extra dev
cp .env.example .env

# Knowledge base
uv run fitness-kb list
uv run fitness-kb index-all
uv run fitness-kb search "how should I train chest for hypertrophy" --agent training -k 3

# Agent system
uv run fitness start --user-id user1
uv run fitness checkin --user-id user1
uv run fitness status --user-id user1

# Regenerate files without re-running agents
uv run fitness export-mesocycle --user-id user1
uv run fitness export-nutrition --user-id user1
uv run fitness export-progress --user-id user1
```

Read the full demo in [docs/DEMO.en.md](docs/DEMO.en.md). Spanish version: [docs/DEMO.md](docs/DEMO.md).

## Use Cases

- Build an AI personal trainer.
- Create a searchable fitness knowledge base with RAG.
- Generate validated structures for training and nutrition plans.
- Experiment with Pydantic models for fitness products.
- Analyze creator content and convert it into indexable sources.

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
- LangGraph and Claude API for the agent phase

## Installation

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra dev

cp .env.example .env
```

Edit `.env` if you plan to use external providers:

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

## Project Structure

```text
cli/                    fitness-kb command-line interface
data/                   Auxiliary structured data
docs/                   Demos and product documentation
scripts/                Ingestion/classification scripts
src/config/             Project configuration
src/knowledge/          RAG, sources, registry, indexing, retrieval
src/models/             Fitness-domain Pydantic models
src/agents/             Specialized agents (intake, assessment, training, nutrition, progress)
src/generators/         XLSX/PDF generators (mesocycle, nutrition, progress)
src/graph/              LangGraph orchestration with SQLite checkpoints
src/db/                 SQLite persistence (connection and repositories)
tests/                  Test suite
```

## Quality

```bash
uv run ruff check .
uv run pytest
```

The suite covers chunking, indexing, retrieval, registry sync, fitness models, validators, agents, database, and graph.

## Roadmap

The public roadmap is in [ROADMAP.en.md](ROADMAP.en.md). Spanish version: [ROADMAP.md](ROADMAP.md).

Useful contributions right now:

- Improve examples.
- Add scientific sources with clean metadata.
- Create test cases for agents.
- Build the non-technical user interface (Telegram bot or web app).
- Prepare a reproducible web demo or notebook.

## Contributing

Read [CONTRIBUTING.en.md](CONTRIBUTING.en.md) to set up the environment, run checks, and propose changes. Spanish version: [CONTRIBUTING.md](CONTRIBUTING.md).

## Suggested GitHub Topics

`fitness`, `ai-agents`, `rag`, `langchain`, `pydantic`, `nutrition`, `workout-planner`, `personal-trainer`, `spanish`, `knowledge-base`

## License

MIT. See [LICENSE](LICENSE).
