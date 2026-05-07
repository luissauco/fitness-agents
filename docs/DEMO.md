# Demo

[English](DEMO.en.md) | Espanol

Esta demo muestra el flujo minimo para entender `fitness-agents`: preparar el entorno, listar fuentes, indexarlas y hacer una busqueda semantica.

## 1. Preparar El Entorno

```bash
uv sync --extra dev
cp .env.example .env
```

Para las funciones locales de RAG no necesitas una API key. La clave de Anthropic se usa en la fase de agentes.

## 2. Explorar La Base De Conocimiento

```bash
uv run fitness-kb list
```

Veras una tabla con fuentes registradas, autores, tipo documental, topics y fiabilidad.

## 3. Indexar

```bash
uv run fitness-kb index-all
uv run fitness-kb stats
```

`index-all` parte los documentos en chunks, calcula embeddings y persiste la coleccion local en ChromaDB.

## 4. Buscar Contexto Para Un Agente

```bash
uv run fitness-kb search "como entrenar pectoral para hipertrofia" --agent training -k 3
```

Salida esperada, abreviada:

```text
---
[Fuente: ... | Autor: ... | Tipo: video_transcript | Fiabilidad: expert_opinion]
...
---
```

Tambien puedes filtrar manualmente:

```bash
uv run fitness-kb search "deficit calorico agresivo" --topic cutting --topic nutrition -k 5
uv run fitness-kb search "fatiga y volumen de entrenamiento" --reliability-min expert_opinion
```

## 5. Usar Los Modelos Desde Python

```python
from src.models import Questionnaire, UserProfile

questionnaire = Questionnaire.get_default()
print(questionnaire.required_question_ids())

# UserProfile y el resto de modelos estan pensados para recibir datos ya
# normalizados desde intake, formularios o agentes.
print(UserProfile)
```

## 6. Ingerir Un Video

```bash
uv run fitness-kb ingest-video "https://www.tiktok.com/@usuario/video/..." \
  --topics hypertrophy,biomechanics \
  --author "Autor"
```

Para lotes grandes:

```bash
uv run fitness-kb list-profile "https://www.tiktok.com/@usuario" --output videos.txt
# Edita videos.txt y deja solo las URLs deseadas.
uv run fitness-kb ingest-from-list videos.txt --topics hypertrophy --no-index
uv run fitness-kb sync-registry --dry-run
```

## 7. Checks

```bash
uv run ruff check .
uv run pytest
```

Si estas preparando una PR, ejecuta ambos antes de subirla.
