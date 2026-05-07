# Contributing

English | [Espanol](CONTRIBUTING.md)

Thanks for helping improve `fitness-agents`. The project is still early, so the most valuable contributions are the ones that make the system easier to try, validate, or extend.

## Local Setup

```bash
git clone https://github.com/luissauco/fitness-agents.git
cd fitness-agents

uv sync --extra dev
cp .env.example .env
```

## Workflow

```bash
git checkout -b feature/my-change
uv run ruff check .
uv run pytest
```

Open a small PR and describe:

- What problem it solves.
- Which main files it touches.
- How you tested it.
- Any limitations or pending decisions.

## Style

- Prefer small, reviewable changes.
- Use Pydantic models when adding structured data.
- Avoid committing generated outputs, especially `output/`, caches, and logs.
- Add tests when changing models, validators, registry, indexing, or retrieval.
- Keep Spanish as the primary language for user-facing product content, but English docs are welcome.

## Adding RAG Sources

Sources live in `src/knowledge/data/transcripts/` and are registered in `src/knowledge/data/registry.json`.

Each transcript should include front matter similar to:

```yaml
---
id: video-example-hypertrophy
title: Example about hypertrophy
author: Author
source_type: video_transcript
topics: [hypertrophy, biomechanics]
reliability: expert_opinion
language: es
date_published: 2026-01-01
url: https://example.com/video
summary: ""
---
```

Then sync and test:

```bash
uv run fitness-kb sync-registry --dry-run
uv run fitness-kb index video-example-hypertrophy
```

## Good First PR Ideas

- Improve examples in `docs/DEMO.en.md` or `docs/DEMO.md`.
- Add model validation tests.
- Document a scientific source with clean metadata.
- Create small fixtures for agents.
- Improve CLI error messages.
- Add export examples once generators exist.

## PR Checklist

- [ ] I ran `uv run ruff check .`.
- [ ] I ran `uv run pytest`.
- [ ] I updated docs if public usage changed.
- [ ] I did not include secrets, caches, logs, or generated files.
