"""Clase base para todos los agentes del sistema fitness-agents.

Define el contrato común: cada agente declara su `name`, su `model` de Claude,
opcionalmente su `agent_type` para consultar el RAG, y debe implementar `run`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod  # noqa: F401  (abstractmethod queda para `model`)
from pathlib import Path
from typing import Any, ClassVar, Final

from src.agents.claude_client import ClaudeClient
from src.config.settings import PROJECT_ROOT, Settings
from src.knowledge.retriever import AgentType, KnowledgeRetriever

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Directorio donde viven los system prompts de cada agente.
_PROMPTS_DIR: Final[Path] = PROJECT_ROOT / "src" / "config" / "prompts"


class BaseAgent(ABC):
    """Clase base para los agentes orquestados por LangGraph.

    Cada subclase fija `name` y `agent_type` como `ClassVar` y expone su modelo
    de Claude vía la property `model` (lo más habitual: leer de `settings`).
    Los agentes que no consulten el RAG dejan `agent_type = None`.
    """

    name: ClassVar[str]
    agent_type: ClassVar[AgentType | None] = None

    def __init__(
        self,
        claude_client: ClaudeClient,
        retriever: KnowledgeRetriever,
        settings: Settings,
    ) -> None:
        """Inyecta dependencias y carga el system prompt del agente."""
        self.claude: ClaudeClient = claude_client
        self.retriever: KnowledgeRetriever = retriever
        self.settings: Settings = settings
        self.system_prompt: str = self._load_system_prompt()

    # ------------------------------------------------------------------ Modelo

    @property
    @abstractmethod
    def model(self) -> str:
        """Modelo de Claude que usa el agente (leído típicamente de `settings`)."""

    # --------------------------------------------------------------- Prompts

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde `src/config/prompts/{name}.md`.

        Si el fichero no existe, registra un warning y devuelve un string vacío.
        Esto permite construir agentes en tests sin tener que poblar todos los
        prompts.
        """
        path: Path = _PROMPTS_DIR / f"{self.name}.md"
        if not path.is_file():
            _logger.warning(
                "base_agent.prompt_missing",
                extra={"agent": self.name, "path": str(path)},
            )
            return ""
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ RAG

    async def get_rag_context(self, query: str, k: int = 5) -> str:
        """Consulta el RAG con el `agent_type` del agente.

        Si el agente no tiene `agent_type` (ej. Intake), devuelve cadena vacía.
        El retriever es síncrono; lo envolvemos en una corrutina para mantener
        coherencia con la interfaz async del resto del sistema.
        """
        if self.agent_type is None:
            return ""
        return self.retriever.retrieve_for_agent(query, self.agent_type, k=k)

    # --------------------------------------------------------------- API

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Punto de entrada por defecto. Los agentes con flujo one-shot lo
        implementan; los conversacionales (p. ej. Intake) exponen métodos
        propios y dejan este método como `NotImplementedError`."""
        raise NotImplementedError(
            f"{type(self).__name__} no implementa `run`. Usa la API específica del agente."
        )
