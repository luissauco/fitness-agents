# Contribuir

Gracias por querer mejorar `fitness-agents`. El proyecto esta en una fase temprana, asi que las contribuciones mas valiosas son las que hacen el sistema mas facil de probar, validar o ampliar.

## Setup Local

```bash
git clone https://github.com/luissauco/fitness-agents.git
cd fitness-agents

uv sync --extra dev
cp .env.example .env
```

## Flujo De Trabajo

```bash
git checkout -b feature/mi-cambio
uv run ruff check .
uv run pytest
```

Abre una PR pequena y describe:

- Que problema resuelve.
- Que archivos principales toca.
- Como lo probaste.
- Cualquier limitacion o decision pendiente.

## Estilo

- Prefiere cambios pequenos y faciles de revisar.
- Usa modelos Pydantic cuando anadas datos estructurados.
- Evita salidas generadas en Git, especialmente `output/`, caches y logs.
- Anade tests cuando cambies modelos, validadores, registry, indexacion o recuperacion.
- Mantener el espanol como idioma principal para documentacion de usuario.

## Anadir Fuentes Al RAG

Las fuentes viven en `src/knowledge/data/transcripts/` y se registran en `src/knowledge/data/registry.json`.

Cada transcripcion debe incluir front matter parecido a:

```yaml
---
id: video-ejemplo-hipertrofia
title: Ejemplo sobre hipertrofia
author: Autor
source_type: video_transcript
topics: [hypertrophy, biomechanics]
reliability: expert_opinion
language: es
date_published: 2026-01-01
url: https://example.com/video
summary: ""
---
```

Despues sincroniza y prueba:

```bash
uv run fitness-kb sync-registry --dry-run
uv run fitness-kb index video-ejemplo-hipertrofia
```

## Ideas Buenas Para Primeras PRs

- Mejorar ejemplos en `docs/DEMO.md`.
- Anadir tests de validacion para modelos.
- Documentar una fuente cientifica con metadata limpia.
- Crear fixtures pequenos para agentes.
- Mejorar mensajes de error del CLI.
- Anadir ejemplos de exportacion cuando existan los generadores.

## Checklist De PR

- [ ] He ejecutado `uv run ruff check .`.
- [ ] He ejecutado `uv run pytest`.
- [ ] He actualizado docs si cambia el uso publico.
- [ ] No he incluido secretos, caches, logs ni archivos generados.
