# Demo

English | [Espanol](DEMO.md)

This demo shows the minimum flow for understanding `fitness-agents`: prepare the environment, list sources, index them, and run semantic search.

## 1. Prepare The Environment

```bash
uv sync --extra dev
cp .env.example .env
```

You do not need an API key for the local RAG features. The Anthropic key is used in the agent phase.

## 2. Explore The Knowledge Base

```bash
uv run fitness-kb list
```

You will see a table with registered sources, authors, document type, topics, and reliability.

## 3. Index Sources

```bash
uv run fitness-kb index-all
uv run fitness-kb stats
```

`index-all` splits documents into chunks, calculates embeddings, and persists the local collection in ChromaDB.

## 4. Retrieve Context For An Agent

```bash
uv run fitness-kb search "how should I train chest for hypertrophy" --agent training -k 3
```

Expected output, shortened:

```text
---
[Fuente: ... | Autor: ... | Tipo: video_transcript | Fiabilidad: expert_opinion]
...
---
```

You can also filter manually:

```bash
uv run fitness-kb search "aggressive calorie deficit" --topic cutting --topic nutrition -k 5
uv run fitness-kb search "fatigue and training volume" --reliability-min expert_opinion
```

## 5. Use The Models From Python

```python
from src.models import Questionnaire, UserProfile

questionnaire = Questionnaire.get_default()
print(questionnaire.required_question_ids())

# UserProfile and the rest of the models are designed to receive normalized
# data from intake flows, forms, or agents.
print(UserProfile)
```

## 6. Ingest A Video

```bash
uv run fitness-kb ingest-video "https://www.tiktok.com/@user/video/..." \
  --topics hypertrophy,biomechanics \
  --author "Author"
```

For larger batches:

```bash
uv run fitness-kb list-profile "https://www.tiktok.com/@user" --output videos.txt
# Edit videos.txt and keep only the URLs you want.
uv run fitness-kb ingest-from-list videos.txt --topics hypertrophy --no-index
uv run fitness-kb sync-registry --dry-run
```

## 7. Checks

```bash
uv run ruff check .
uv run pytest
```

If you are preparing a PR, run both before pushing.
