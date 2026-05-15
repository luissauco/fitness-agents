"""Factoría de dependencias para los comandos de la CLI.

Construye una sola vez el `ClaudeClient`, el retriever, el `AgentBundle` con
los cinco agentes y los repositorios SQLite. Se reutiliza desde cualquier
comando para evitar duplicar el wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents.assessment import AssessmentAgent
from src.agents.claude_client import ClaudeClient
from src.agents.intake import IntakeAgent
from src.agents.nutrition import NutritionAgent
from src.agents.progress import ProgressAgent
from src.agents.training import TrainingAgent
from src.config.settings import Settings, get_settings
from src.db.connection import init_schema
from src.db.repositories import (
    BodyAssessmentRepository,
    MesocycleRepository,
    NutritionPlanRepository,
    ProgressLogRepository,
    TelegramUserRepository,
    UserProfileRepository,
)
from src.graph.workflow import AgentBundle, build_workflow
from src.knowledge.embeddings import EmbeddingManager
from src.knowledge.retriever import KnowledgeRetriever


@dataclass
class Repositories:
    """Conjunto de repositorios SQLite usados por los comandos."""

    user_profile: UserProfileRepository
    body_assessment: BodyAssessmentRepository
    mesocycle: MesocycleRepository
    nutrition_plan: NutritionPlanRepository
    progress_log: ProgressLogRepository
    telegram_user: TelegramUserRepository


@dataclass
class Container:
    """Contenedor de dependencias compartidas entre comandos."""

    settings: Settings
    bundle: AgentBundle
    repos: Repositories
    # workflow compilado sin checkpointer (la CLI lo usa directamente;
    # el bot construye uno propio con checkpointer en post_init).
    workflow: object = field(default=None, repr=False)


def build_container() -> Container:
    """Construye los agentes, retriever y repositorios. Inicializa el esquema."""
    settings: Settings = get_settings()
    init_schema()

    embedding_manager: EmbeddingManager = EmbeddingManager(settings)
    retriever: KnowledgeRetriever = KnowledgeRetriever(
        settings=settings, embedding_manager=embedding_manager
    )
    claude: ClaudeClient = ClaudeClient(settings)

    bundle: AgentBundle = AgentBundle(
        intake=IntakeAgent(claude_client=claude, retriever=retriever, settings=settings),
        assessment=AssessmentAgent(claude_client=claude, retriever=retriever, settings=settings),
        training=TrainingAgent(claude_client=claude, retriever=retriever, settings=settings),
        nutrition=NutritionAgent(claude_client=claude, retriever=retriever, settings=settings),
        progress=ProgressAgent(claude_client=claude, retriever=retriever, settings=settings),
    )
    repos: Repositories = Repositories(
        user_profile=UserProfileRepository(),
        body_assessment=BodyAssessmentRepository(),
        mesocycle=MesocycleRepository(),
        nutrition_plan=NutritionPlanRepository(),
        progress_log=ProgressLogRepository(),
        telegram_user=TelegramUserRepository(),
    )
    return Container(settings=settings, bundle=bundle, repos=repos, workflow=build_workflow(bundle))


def persist_artifacts(state: dict, repos: Repositories) -> list[str]:
    """Persiste los artefactos presentes en `state`. Devuelve nombres guardados."""
    saved: list[str] = []
    if (profile := state.get("user_profile")) is not None:
        repos.user_profile.save(profile)
        saved.append("user_profile")
    if (assessment := state.get("body_assessment")) is not None:
        repos.body_assessment.save(assessment)
        saved.append("body_assessment")
    if (mesocycle := state.get("current_mesocycle")) is not None:
        repos.mesocycle.save(mesocycle)
        saved.append("mesocycle")
    if (plan := state.get("current_nutrition_plan")) is not None:
        repos.nutrition_plan.save(plan)
        saved.append("nutrition_plan")
    for log in state.get("progress_logs") or []:
        repos.progress_log.save(log)
    if state.get("progress_logs"):
        saved.append("progress_logs")
    return saved
