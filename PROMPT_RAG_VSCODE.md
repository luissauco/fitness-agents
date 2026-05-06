# PROMPT PARA CREAR LA BASE DE CONOCIMIENTO RAG EN VSCODE

> Copia y pega este prompt en tu asistente de IA en VSCode (Claude, Cursor, Copilot, etc.)
> Ajusta las secciones marcadas con [AJUSTAR] según tu preferencia.

---

## PROMPT:

```
Eres un ingeniero senior de Python especializado en sistemas RAG y aplicaciones de IA. Vamos a construir el módulo de base de conocimiento (RAG) para un sistema multi-agente de nutrición y entrenamiento personal.

## CONTEXTO DEL PROYECTO

El proyecto "fitness-agents" es un sistema multi-agente que actúa como nutricionista y entrenador personal. Tiene 5 agentes especializados (intake, evaluación corporal, entrenamiento, nutrición y progreso) coordinados por un orquestador LangGraph. Todos los agentes consultan una base de conocimiento RAG para fundamentar sus decisiones con evidencia científica.

La base de conocimiento se nutre principalmente del contenido de Fran Pérez Jurado (@franperezjurado en TikTok), un entrenador personal y nutricionista titulado por la Universidad de Nebrija, campeón de España IFBB en men's physique, especializado en hipertrofia basada en ciencia y biomecánica. También incluye los estudios científicos que él cita y otras fuentes de referencia en entrenamiento y nutrición deportiva basada en evidencia.

## QUÉ NECESITO QUE HAGAS

Crea paso a paso la estructura completa del módulo RAG. Sigue este orden exacto:

### PASO 1: Setup del proyecto base

Crea la estructura de carpetas del proyecto completo (solo las carpetas y archivos __init__.py necesarios por ahora, el resto de módulos fuera del RAG se implementarán después):

```
fitness-agents/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── src/
│   ├── __init__.py
│   ├── knowledge/          ← FOCO DE ESTE PROMPT
│   │   ├── __init__.py
│   │   ├── indexer.py
│   │   ├── retriever.py
│   │   ├── sources.py
│   │   ├── chunker.py
│   │   ├── embeddings.py
│   │   └── data/
│   │       ├── transcripts/
│   │       ├── studies/
│   │       ├── guidelines/
│   │       └── registry.json
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── agents/
│   │   └── __init__.py
│   ├── models/
│   │   └── __init__.py
│   ├── tools/
│   │   └── __init__.py
│   ├── generators/
│   │   └── __init__.py
│   ├── graph/
│   │   └── __init__.py
│   └── db/
│       └── __init__.py
├── cli/
│   └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_knowledge/
│       ├── __init__.py
│       ├── test_indexer.py
│       ├── test_retriever.py
│       └── test_chunker.py
└── output/
```

En `pyproject.toml` usa uv como gestor de paquetes. Dependencias necesarias:
- anthropic (SDK de Claude)
- chromadb (vector store)
- langchain, langchain-anthropic, langchain-community, langchain-chroma
- pydantic, pydantic-settings
- python-dotenv
- rich (para CLI)
- typer
- openpyxl (para futura generación de Excel)
- pytest, pytest-asyncio (testing)
- yt-dlp (para descargar transcripciones de vídeos)
- whisper o faster-whisper (para transcribir audio si no hay subtítulos)

### PASO 2: Configuración (`src/config/settings.py`)

Crea un módulo de settings con pydantic-settings que lea de .env:

```python
# Variables necesarias:
ANTHROPIC_API_KEY: str
CHROMA_PERSIST_DIR: str = "./data/chroma_db"
EMBEDDING_MODEL: str = "text-embedding-3-small"  # o el que uses
CHUNK_SIZE: int = 1000
CHUNK_OVERLAP: int = 200
COLLECTION_NAME: str = "fitness_knowledge"
```

Usa un patrón singleton o lru_cache para que settings se instancie una sola vez.

### PASO 3: Modelos de documentos (`src/knowledge/sources.py`)

Define los modelos Pydantic para los documentos de la base de conocimiento:

```python
from enum import Enum
from pydantic import BaseModel
from datetime import date

class SourceType(str, Enum):
    VIDEO_TRANSCRIPT = "video_transcript"
    SCIENTIFIC_STUDY = "scientific_study"
    GUIDELINE = "guideline"
    BOOK_EXCERPT = "book_excerpt"
    ARTICLE = "article"

class Topic(str, Enum):
    HYPERTROPHY = "hypertrophy"
    NUTRITION = "nutrition"
    PERIODIZATION = "periodization"
    BIOMECHANICS = "biomechanics"
    EXERCISE_SELECTION = "exercise_selection"
    VOLUME = "volume"
    INTENSITY = "intensity"
    REST_PAUSE = "rest_pause"
    SUPERSETS = "supersets"
    BODY_COMPOSITION = "body_composition"
    SUPPLEMENTS = "supplements"
    RECOVERY = "recovery"
    NEAT_CARDIO = "neat_cardio"
    MACROS = "macros"
    MEAL_PLANNING = "meal_planning"
    CUTTING = "cutting"
    BULKING = "bulking"
    RECOMPOSITION = "recomposition"
    DELOAD = "deload"
    PROGRESSIVE_OVERLOAD = "progressive_overload"
    MUSCLE_LENGTH = "muscle_length"
    RESISTANCE_PROFILE = "resistance_profile"

class Reliability(str, Enum):
    PEER_REVIEWED = "peer_reviewed"
    META_ANALYSIS = "meta_analysis"
    EXPERT_OPINION = "expert_opinion"
    ANECDOTAL = "anecdotal"

class KnowledgeSource(BaseModel):
    id: str  # slug único
    title: str
    author: str
    source_type: SourceType
    topics: list[Topic]
    reliability: Reliability
    date_published: date | None = None
    url: str | None = None
    file_path: str  # ruta relativa al archivo de texto
    language: str = "es"
    summary: str | None = None  # resumen breve del contenido
```

Crea también un `registry.json` en `data/` que actúe como catálogo de todas las fuentes indexadas. Incluye un script o función para cargar/actualizar el registry.

### PASO 4: Chunking inteligente (`src/knowledge/chunker.py`)

Implementa un chunker que:
- Use `RecursiveCharacterTextSplitter` de LangChain como base
- Tenga separadores especiales para transcripciones de vídeo (por tema/pregunta)
- Tenga separadores para papers científicos (por sección: abstract, methods, results, discussion)
- Añada metadata a cada chunk:
  - `source_id`: referencia al KnowledgeSource
  - `chunk_index`: posición del chunk en el documento
  - `topics`: heredados de la fuente
  - `reliability`: heredada de la fuente
  - `author`: heredado de la fuente
  - `source_type`: heredado de la fuente
- Tamaño de chunk: 1000 tokens con 200 de overlap (configurable desde settings)
- Función para preprocesar texto antes de chunking (limpiar timestamps, [música], etc.)

### PASO 5: Embeddings (`src/knowledge/embeddings.py`)

Implementa el módulo de embeddings:
- Usa los embeddings de Anthropic vía Voyager si están disponibles, si no, usa sentence-transformers con un modelo multilingüe como "paraphrase-multilingual-MiniLM-L12-v2" (porque el contenido es en español)
- Encapsula la lógica en una clase `EmbeddingManager` que abstraiga el proveedor
- Incluye caché local de embeddings ya calculados para no recalcular

IMPORTANTE: Evalúa qué opción de embeddings es más práctica y coste-efectiva para un proyecto local. Si usas sentence-transformers, no necesitas API key para embeddings (solo para el LLM). Decide tú la mejor opción y justifícala en un comentario.

### PASO 6: Indexador (`src/knowledge/indexer.py`)

Implementa la clase `KnowledgeIndexer`:

```python
class KnowledgeIndexer:
    """Indexa documentos de conocimiento en ChromaDB."""
    
    def __init__(self, settings, embedding_manager):
        ...
    
    def index_source(self, source: KnowledgeSource) -> int:
        """Indexa una fuente completa. Retorna número de chunks creados."""
        # 1. Leer el archivo de texto
        # 2. Preprocesar
        # 3. Chunkear con metadata
        # 4. Generar embeddings
        # 5. Upsert en ChromaDB (idempotente por source_id + chunk_index)
        ...
    
    def index_all(self, registry_path: str = "data/registry.json") -> dict:
        """Indexa todas las fuentes del registry. Retorna stats."""
        ...
    
    def reindex_source(self, source_id: str) -> int:
        """Elimina chunks existentes de una fuente y reindexa."""
        ...
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de la colección."""
        ...
    
    def delete_source(self, source_id: str) -> int:
        """Elimina una fuente del índice."""
        ...
```

Requisitos:
- Operaciones idempotentes (reindexar no duplica)
- Logging con Rich para mostrar progreso
- Manejo de errores robusto (archivo no encontrado, encoding, etc.)
- ChromaDB en modo persistente (disco) para no perder el índice

### PASO 7: Retriever (`src/knowledge/retriever.py`)

Implementa la clase `KnowledgeRetriever`:

```python
class KnowledgeRetriever:
    """Recupera conocimiento relevante del vector store."""
    
    def __init__(self, settings, embedding_manager):
        ...
    
    def retrieve(
        self,
        query: str,
        topics: list[Topic] | None = None,
        source_types: list[SourceType] | None = None,
        reliability_min: Reliability | None = None,
        author: str | None = None,
        k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[RetrievedChunk]:
        """
        Búsqueda semántica con filtros opcionales de metadata.
        
        Retorna chunks ordenados por relevancia, cada uno con:
        - content: texto del chunk
        - metadata: toda la metadata del chunk
        - score: similaridad coseno
        - source: referencia a la KnowledgeSource original
        """
        ...
    
    def retrieve_for_agent(
        self,
        query: str,
        agent_type: str,  # "training", "nutrition", "assessment", "progress"
        k: int = 5,
    ) -> str:
        """
        Retrieval preconfigurado por tipo de agente.
        Aplica filtros de topics relevantes automáticamente.
        Retorna el contexto formateado como string para inyectar en el prompt.
        
        Mapeo agente → topics:
        - training: hypertrophy, periodization, volume, intensity, exercise_selection, 
                     biomechanics, rest_pause, supersets, deload, progressive_overload,
                     muscle_length, resistance_profile
        - nutrition: nutrition, macros, meal_planning, supplements, cutting, bulking,
                     recomposition, body_composition
        - assessment: body_composition, nutrition (para TDEE)
        - progress: todos los topics (necesita contexto amplio)
        """
        ...
    
    def format_context(self, chunks: list[RetrievedChunk]) -> str:
        """
        Formatea los chunks recuperados como contexto para el LLM.
        Formato:
        
        ---
        [Fuente: {title} | Autor: {author} | Tipo: {source_type} | Fiabilidad: {reliability}]
        {content}
        ---
        """
        ...
```

### PASO 8: Contenido inicial de la base de conocimiento

Crea archivos de guidelines en `data/guidelines/` con el conocimiento base extraído y organizado. Estos son documentos que YO redactaré basándome en el contenido de Fran Pérez Jurado, pero necesito que crees los archivos plantilla con la estructura:

```
data/guidelines/
├── 01_principios_hipertrofia.md
├── 02_seleccion_ejercicios_biomecanica.md
├── 03_periodizacion_mesociclos.md
├── 04_tecnicas_intensificacion.md
├── 05_volumen_efectivo.md
├── 06_nutricion_deportiva_base.md
├── 07_fases_cut_bulk_recomp.md
├── 08_suplementacion.md
├── 09_neat_cardio.md
├── 10_evaluacion_progreso.md
```

Para cada archivo, incluye:
- Un header con metadata en YAML front matter (título, author, topics, reliability)
- Secciones vacías con headers descriptivos de lo que debo rellenar
- Comentarios indicando qué tipo de información va en cada sección
- Un par de ejemplos de contenido para que yo entienda el formato esperado

IMPORTANTE: No inventes contenido de Fran Pérez Jurado. Deja los archivos como plantillas con indicaciones claras de qué contenido debo añadir yo. Solo incluye contenido que sea conocimiento general bien establecido en ciencia del ejercicio.

### PASO 9: Script de ingesta de vídeos

Crea un script en `src/knowledge/video_ingest.py` que:
1. Reciba una URL de TikTok o YouTube
2. Descargue el audio con yt-dlp
3. Transcriba con Whisper (faster-whisper preferiblemente)
4. Limpie la transcripción (quitar timestamps, ruido)
5. Genere un archivo .md en `data/transcripts/` con front matter
6. Registre la fuente en `registry.json`
7. Indexe automáticamente el nuevo documento

Incluye un CLI command simple para ejecutar:
```bash
python -m src.knowledge.video_ingest "https://tiktok.com/@franperezjurado/video/XXXXX"
```

### PASO 10: Tests

Crea tests para:
- `test_chunker.py`: 
  - Chunking de texto plano respeta tamaño y overlap
  - Metadata se propaga correctamente a cada chunk
  - Preprocesamiento limpia timestamps y ruido
  - Separadores especiales funcionan para transcripciones
  
- `test_indexer.py`:
  - Indexación de una fuente crea chunks en ChromaDB
  - Reindexación es idempotente (no duplica)
  - Stats retorna conteos correctos
  - Delete elimina solo chunks de la fuente indicada
  
- `test_retriever.py`:
  - Búsqueda sin filtros retorna k resultados
  - Filtro por topic reduce resultados a los relevantes
  - Filtro por reliability excluye fuentes de menor fiabilidad
  - retrieve_for_agent aplica los filtros correctos por tipo
  - format_context genera string bien estructurado

Usa fixtures con datos de ejemplo (no necesitan embeddings reales, puedes mockear ChromaDB).

### PASO 11: Script de CLI para gestión

Crea `cli/knowledge_cli.py` con Typer:
```
fitness-kb index-all          # Indexa todo el registry
fitness-kb index <source_id>  # Indexa una fuente específica
fitness-kb search <query>     # Búsqueda rápida de prueba
fitness-kb stats              # Muestra estadísticas del índice
fitness-kb ingest-video <url> # Descarga, transcribe e indexa un vídeo
fitness-kb list               # Lista todas las fuentes registradas
```

Usa Rich para output bonito en terminal (tablas, progress bars, colores).

## REQUISITOS TÉCNICOS GENERALES

- Python 3.12+
- Type hints en todas las funciones y clases
- Docstrings en español en todas las funciones públicas
- Logging estructurado con loguru o logging estándar
- Manejo de errores con excepciones custom cuando sea apropiado
- Código async donde tenga sentido (especialmente para API calls)
- Compatible con el resto del proyecto que usará LangGraph

## ESTILO DE CÓDIGO

- Formatter: ruff format
- Linter: ruff check
- Line length: 100
- Imports ordenados (isort integrado en ruff)
- Clases con responsabilidad única
- Funciones pequeñas y descriptivas
- No usar `print()` directamente, siempre logging o Rich console

## ORDEN DE IMPLEMENTACIÓN

Empieza por el paso 1 y ve secuencialmente. Después de cada paso, espera mi confirmación antes de continuar al siguiente. Si tienes dudas sobre alguna decisión técnica, pregúntame antes de implementar.

Empecemos por el PASO 1: crea toda la estructura de carpetas y el pyproject.toml.
```

---

## NOTAS DE USO

### Cómo alimentar la base de conocimiento después

Una vez que el RAG esté construido, el flujo para añadir contenido será:

1. **Vídeos de Fran Pérez Jurado:**
   ```bash
   fitness-kb ingest-video "https://tiktok.com/@franperezjurado/video/XXXXX"
   ```
   Esto descarga → transcribe → limpia → indexa automáticamente.

2. **Guidelines manuales:**
   - Edita los archivos .md en `data/guidelines/`
   - Ejecuta `fitness-kb index-all` para reindexar

3. **Estudios científicos:**
   - Coloca el PDF en `data/studies/`
   - Añade entrada en `registry.json`
   - Ejecuta `fitness-kb index <source_id>`

### Verificar que funciona

```bash
# Después de indexar contenido:
fitness-kb search "cuántas series efectivas por grupo muscular"
fitness-kb search "distribución de macros en fase de definición"
fitness-kb search "ejercicios para espalda alta biomecánica"
```
