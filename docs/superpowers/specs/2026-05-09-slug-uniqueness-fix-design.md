# Fix: Unicidad de slugs en ingesta de vídeos

**Fecha:** 2026-05-09
**Alcance:** `src/knowledge/video_ingest.py` + migración de 6 vídeos con colisión

---

## Problema

`_slugify` trunca el texto a 60 caracteres. Cuando el título llena los 60 chars, el
`video_id` que se concatena al final queda fuera del corte. Resultado: dos vídeos TikTok
con el mismo título (habitual en series del mismo creador) generan el mismo slug y
colisionan en registry y en disco.

Afectados actualmente: 3 pares de vídeos → 3 IDs compartidos.

---

## Diseño

### Cambio en código (`video_ingest.py`)

Añadir `_make_slug(title, video_id)` que:
1. Slugifica el `video_id` (solo caracteres seguros).
2. Calcula el espacio disponible para el título: `max(10, 54 - len(id_part))`.
3. Trunca el título a ese espacio.
4. Devuelve `title_part + "-" + id_part`.

Esto garantiza que el `video_id` siempre aparece en el slug. Como el `video_id` de
yt-dlp es único por plataforma (TikTok, YouTube…), el slug resultante es globalmente único.

Longitud máxima resultante:
- slug ≤ 35 + 1 + 19 = 55 chars (caso TikTok, ID de 19 dígitos)
- `source_id` = "video-" + slug ≤ 61 chars — dentro del límite `max_length=80`

Reemplaza la línea actual en `_persist_transcript`:
```python
# Antes
slug = _slugify(f"{title}-{video_id}" if video_id else title)
# Después
slug = _make_slug(title, video_id) if video_id else _slugify(title)
```

No hay cambios en `sources.py`, `registry_sync.py`, ni en ChromaDB.

### Migración de vídeos con colisión

Los 3 pares afectados son:

| Par | Video ID A | Video ID B | Slug compartido actual |
|-----|-----------|-----------|------------------------|
| dorsal | 7320321936054095137 | 7317002680868637985 | `video-hablemos-de-el-dorsal-...-entr` |
| mitos simple | 7492889959226150167 | 7482877001548795138 | `video-desmintiendo-mitos-del-gimnasio-gimnasio-...` |
| mitos ciencia | 7515147905691438358 | 7459132651128065313 | `video-desmintiendo-mitos-del-gimnasio-basado-...` |

Pasos de migración:
1. Eliminar los 3 `.md` con IDs colisionados del directorio `transcripts/`.
2. Borrar esos 3 IDs del `registry.json` (manualmente o vía script).
3. Reingestar los 6 vídeos → 6 nuevos `.md` con IDs únicos.
4. Ejecutar `sync-registry` para verificar consistencia.
5. Verificar que registry tiene 280 entradas.

---

## Criterios de éxito

- `python3 -c "..."` comparando URLs del txt con registry devuelve `Faltan: 0`.
- Registry total = 280.
- No existen dos entradas en registry con el mismo `id`.
- Tests existentes pasan (`pytest tests/`).
