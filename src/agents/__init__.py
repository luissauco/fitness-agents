"""Agentes especializados del sistema fitness-agents.

Reexporta la infraestructura compartida (`ClaudeClient`, `BaseAgent`) para que
los nodos del grafo y los tests puedan importar de forma plana.
"""

from src.agents.base import BaseAgent
from src.agents.claude_client import (
    ClaudeClient,
    ClaudeStructuredOutputError,
    image_block_from_path,
)

__all__ = [
    "BaseAgent",
    "ClaudeClient",
    "ClaudeStructuredOutputError",
    "image_block_from_path",
]
