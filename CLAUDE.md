# FITNESS AGENTS — Sistema multi-agente de nutrición y entrenamiento

## Contexto
Sistema multi-agente Python que actúa como nutricionista y entrenador personal.
Realiza seguimiento bisemanal, genera mesociclos de entrenamiento en Excel
(divididos en microciclos semanales) y planes nutricionales en PDF.
Base de conocimiento RAG con contenido de Fran Pérez Jurado y estudios científicos.

## Stack
- Python 3.12+, uv como gestor de paquetes
- LangGraph para orquestación de agentes
- ChromaDB como vector store local
- Claude API (Anthropic) como LLM
- openpyxl para generación de Excel
- Typer + Rich para CLI
- pytest para testing
- ruff como formatter y linter

## Reglas de código
- Docstrings y comentarios en español
- Type hints obligatorios en todas las funciones y métodos
- ruff format + ruff check (line-length=100)
- No usar print(), siempre logging o Rich console
- Async donde tenga sentido (API calls, I/O)
- Tests con pytest para cada módulo nuevo
- Pydantic para todos los modelos de datos
- Clases con responsabilidad única
- Mínimo código necesario, no sobreingeniería

## Estructura del proyecto
src/
knowledge/   ← módulo RAG (FOCO ACTUAL)
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
## Fase actual
Construyendo el módulo RAG (src/knowledge/).
El resto de carpetas solo necesitan __init__.py por ahora.


---

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
