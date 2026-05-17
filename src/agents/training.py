"""Agente generador de mesociclos de entrenamiento.

Pipeline en dos fases:

1. `_design_mesocycle_structure` (LLM, 1 llamada): produce un esqueleto con
   plan de microciclos (progresión RIR/volumen) y plantilla de días.
2. `_populate_microcycle` (LLM, 1 llamada por microciclo): rellena el detalle
   con `Microcycle` ya validable contra el catálogo de ejercicios.

Tras concatenar los microciclos, ejecuta los validators cruzados; si surgen
warnings, registra logs y deja al orquestador decidir si reintentar.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import ClassVar, Final

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.knowledge.retriever import AgentType
from src.models.body_assessment import BodyAssessment
from src.models.exercise_db import Equipment, Exercise, ExerciseDatabase
from src.models.mesocycle import (
    Mesocycle,
    MesocyclePhase,
    Microcycle,
    SplitType,
    WeeklySchedule,
)
from src.models.user_profile import UserProfile
from src.models.validators import (
    validate_equipment_compatibility,
    validate_mesocycle_structure,
)

_logger: Final[logging.Logger] = logging.getLogger(__name__)


# Mapeo días/semana → split por defecto. Determinístico.
_DEFAULT_SPLIT_BY_DAYS: Final[dict[int, SplitType]] = {
    1: "full_body",
    2: "full_body",
    3: "full_body",
    4: "upper_lower",
    5: "torso_legs",
    6: "push_pull_legs",
    7: "push_pull_legs",
}


# ----------------------------------------------------- Estructuras intermedias


class _ExerciseSlot(BaseModel):
    """Hueco para un ejercicio dentro del esqueleto del día."""

    order: int = Field(..., ge=1)
    role: str = Field(..., description="`compound` o `isolation`.")
    primary_muscle: str = Field(..., description="Grupo muscular principal a trabajar.")
    movement_pattern: str = Field(..., description="Patrón de movimiento objetivo.")
    force_profile_preference: str | None = Field(
        default=None, description="Profile preferido (stretched/shortened/mid_range)."
    )
    volume_target_sets: int = Field(..., ge=1, le=10)


class _DayTemplate(BaseModel):
    """Plantilla de un día del split, replicable por microciclo."""

    day_number: int = Field(..., ge=1, le=10)
    day_label: str
    is_rest_day: bool = False
    slots: list[_ExerciseSlot] = Field(default_factory=list)


class _MicrocyclePlan(BaseModel):
    """Plan a alto nivel de un microciclo (progresión sin detalle)."""

    number: int = Field(..., ge=1)
    duration_days: int = Field(default=7, ge=1, le=14)
    is_deload: bool = False
    volume_modifier: float = Field(default=1.0, gt=0, le=2.0)
    intensity_modifier: float = Field(default=1.0, gt=0, le=1.5)
    target_rir_low: int = Field(..., ge=0, le=5)
    target_rir_high: int = Field(..., ge=0, le=5)
    notes: str | None = None


class _MesocycleStructure(BaseModel):
    """Esqueleto de mesociclo: el primer LLM lo produce; el segundo lo detalla."""

    name: str
    phase: MesocyclePhase
    split_type: SplitType
    training_days_per_week: int = Field(..., ge=1, le=7)
    progression_strategy: str
    days_template: list[_DayTemplate] = Field(..., min_length=1)
    microcycles_plan: list[_MicrocyclePlan] = Field(..., min_length=2)


# ----------------------------------------------------------------- TrainingAgent


class TrainingAgent(BaseAgent):
    """Agente que diseña un mesociclo completo de entrenamiento."""

    name: ClassVar[str] = "training"
    agent_type: ClassVar[AgentType | None] = "training"

    @property
    def model(self) -> str:
        """Opus 4.7 con extended thinking: razonamiento profundo sobre estructura."""
        return self.settings.MODEL_OPUS

    # ----------------------------------------------------------------- API pública

    async def run(  # type: ignore[override]
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        previous_mesocycle: Mesocycle | None = None,
        exercise_db: ExerciseDatabase | None = None,
    ) -> Mesocycle:
        """Genera un mesociclo completo coherente con perfil + evaluación."""
        db: ExerciseDatabase = exercise_db or ExerciseDatabase.load()
        available: list[Equipment] = list(profile.gym.available_equipment) or list(Equipment)
        split: SplitType = self._select_split(profile.activity.training_days_per_week)

        rag_context: str = await self._gather_rag_context(profile, assessment, split)
        structure: _MesocycleStructure = await self._design_mesocycle_structure(
            profile, assessment, split, rag_context, previous_mesocycle
        )
        microcycles: list[Microcycle] = await self._populate_microcycles(
            structure=structure,
            db=db,
            available=available,
            profile=profile,
            assessment=assessment,
            rag_context=rag_context,
        )

        mesocycle: Mesocycle = Mesocycle(
            id=uuid.uuid4().hex[:12],
            user_id=profile.id,
            name=structure.name,
            start_date=date.today(),
            phase=structure.phase,
            split_type=structure.split_type,
            training_days_per_week=structure.training_days_per_week,
            microcycles=microcycles,
            weekly_schedule=self._build_weekly_schedule(structure, assessment),
            progression_strategy=structure.progression_strategy,
        )

        self._validate_mesocycle(mesocycle, available, db)
        return mesocycle

    # ------------------------------------------------------------- Determinístico

    def _select_split(self, training_days: int) -> SplitType:
        """Selección determinística del split según días/semana disponibles."""
        if training_days < 1 or training_days > 7:
            raise ValueError(f"training_days fuera de rango: {training_days}")
        return _DEFAULT_SPLIT_BY_DAYS[training_days]

    @staticmethod
    def _build_weekly_schedule(
        structure: _MesocycleStructure, assessment: BodyAssessment
    ) -> WeeklySchedule:
        """Esquema semanal con pasos diarios derivados de la fase recomendada."""
        phase: str = assessment.phase_recommendation.recommended_phase
        train_steps: int = 10500 if phase in ("cut", "minicut") else 10000
        rest_steps: int = 12500 if phase in ("cut", "minicut") else 11500
        days: list[dict] = []
        for tpl in structure.days_template:
            days.append(
                {
                    "day": tpl.day_number,
                    "type": "descanso" if tpl.is_rest_day else "pesas",
                    "steps": rest_steps if tpl.is_rest_day else train_steps,
                }
            )
        return WeeklySchedule(days=days, notes=None)

    # --------------------------------------------------------------- Validación

    def _validate_mesocycle(
        self,
        mesocycle: Mesocycle,
        available: list[Equipment],
        db: ExerciseDatabase,
    ) -> None:
        """Aplica validators cruzados; warnings van al log, no abortan ejecución."""
        struct_warnings: list[str] = validate_mesocycle_structure(mesocycle)
        equip_warnings: list[str] = validate_equipment_compatibility(
            mesocycle, available, database=db
        )
        if struct_warnings:
            _logger.warning(
                "training.structure_warnings",
                extra={"mesocycle": mesocycle.id, "warnings": struct_warnings},
            )
        if equip_warnings:
            _logger.warning(
                "training.equipment_warnings",
                extra={"mesocycle": mesocycle.id, "warnings": equip_warnings},
            )

    # ----------------------------------------------------------------- RAG

    async def _gather_rag_context(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        split: SplitType,
    ) -> str:
        """Combina varias consultas al RAG en un único bloque de contexto."""
        priorities: str = ", ".join(profile.goals.priority_body_areas) or "general"
        phase: str = assessment.phase_recommendation.recommended_phase
        queries: list[str] = [
            f"metodología hipertrofia split {split} volumen efectivo semanal",
            f"selección de ejercicios biomecánica para {priorities}",
            f"progresión RIR cargas mesociclo en fase {phase}",
            "técnicas de intensificación rest-pause superseries myo-reps",
        ]
        chunks: list[str] = []
        for q in queries:
            chunks.append(await self.get_rag_context(q, k=3))
        return "\n\n---\n\n".join(c for c in chunks if c)

    # ------------------------------------------------------- LLM call #1: estructura

    async def _design_mesocycle_structure(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        split: SplitType,
        rag_context: str,
        previous_mesocycle: Mesocycle | None,
    ) -> _MesocycleStructure:
        """Llama a Claude con extended thinking para diseñar el esqueleto."""
        prompt: str = self._build_structure_prompt(
            profile, assessment, split, rag_context, previous_mesocycle
        )
        return await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_model=_MesocycleStructure,
            max_tokens=8192,
            thinking=True,
        )

    @staticmethod
    def _build_structure_prompt(
        profile: UserProfile,
        assessment: BodyAssessment,
        split: SplitType,
        rag_context: str,
        previous_mesocycle: Mesocycle | None,
    ) -> str:
        """Compone el user message para la llamada de diseño."""
        prev: str = (
            (
                f"\n## MESOCICLO ANTERIOR\n"
                f"- Fase: {previous_mesocycle.phase}\n"
                f"- Split: {previous_mesocycle.split_type}\n"
                f"- Microciclos: {len(previous_mesocycle.microcycles)}\n"
                f"- Estrategia previa: {previous_mesocycle.progression_strategy}\n"
            )
            if previous_mesocycle is not None
            else ""
        )
        return (
            "## OBJETIVO\n"
            f"Diseñar el ESQUELETO (no detalle por ejercicio) de un mesociclo de "
            f"entrenamiento para {profile.personal.name}. Devuelve `_MesocycleStructure`.\n"
            "\n## DATOS DEL USUARIO\n"
            f"- {profile.personal.sex}, {profile.personal.age} años, "
            f"{profile.personal.height_cm} cm, {profile.personal.weight_kg} kg\n"
            f"- Objetivo: {profile.goals.primary_goal} — {profile.goals.primary_goal_detail}\n"
            f"- Días entreno/semana: {profile.activity.training_days_per_week}\n"
            f"- Lesiones: {profile.activity.injuries or '—'}\n"
            f"- Zonas prioritarias: {profile.goals.priority_body_areas or '—'}\n"
            "\n## EVALUACIÓN\n"
            f"- Fase recomendada: {assessment.phase_recommendation.recommended_phase}\n"
            f"- TDEE: {assessment.metabolic.tdee} kcal · "
            f"% graso: {assessment.visual.estimated_body_fat_range}\n"
            f"- Puntos débiles: {assessment.visual.weak_points}\n"
            "\n## SPLIT FIJADO\n"
            f"`{split}` (determinístico según días/semana).\n"
            f"{prev}"
            "\n## CONOCIMIENTO RECUPERADO (RAG)\n"
            f"{rag_context}\n"
            "\n## INSTRUCCIONES\n"
            "Define `microcycles_plan` con 4–5 microciclos de carga + 1 descarga "
            "(`is_deload=True`, `volume_modifier ≤ 0.7`). Para cada microciclo "
            "fija `target_rir_low` y `target_rir_high` siguiendo la regla de "
            "progresión del system prompt. Define `days_template` con un día por "
            "sesión del split, listando los huecos (`slots`) de ejercicio que el "
            "siguiente paso rellenará: cada slot indica `order`, `role` "
            "(`compound`/`isolation`), `primary_muscle`, `movement_pattern` y "
            "`volume_target_sets` para el microciclo base.\n"
        )

    # ----------------------------------------------- LLM call #2: detalle por micro

    async def _populate_microcycles(
        self,
        *,
        structure: _MesocycleStructure,
        db: ExerciseDatabase,
        available: list[Equipment],
        profile: UserProfile,
        assessment: BodyAssessment,
        rag_context: str,
    ) -> list[Microcycle]:
        """Llama al LLM una vez por microciclo y devuelve la lista detallada."""
        catalog_blob: str = self._compact_catalog(db, available)
        microcycles: list[Microcycle] = []
        for plan in structure.microcycles_plan:
            micro: Microcycle = await self._populate_microcycle(
                plan=plan,
                structure=structure,
                catalog_blob=catalog_blob,
                profile=profile,
                assessment=assessment,
                rag_context=rag_context,
            )
            microcycles.append(micro)
        return microcycles

    async def _populate_microcycle(
        self,
        *,
        plan: _MicrocyclePlan,
        structure: _MesocycleStructure,
        catalog_blob: str,
        profile: UserProfile,
        assessment: BodyAssessment,
        rag_context: str,
    ) -> Microcycle:
        """Rellena un microciclo concreto generando todos sus `TrainingDay`."""
        prompt: str = (
            "## MICROCICLO A DETALLAR\n"
            f"- Número: {plan.number} · duración: {plan.duration_days} días\n"
            f"- is_deload: {plan.is_deload} · "
            f"volume_modifier: {plan.volume_modifier} · "
            f"intensity_modifier: {plan.intensity_modifier}\n"
            f"- RIR objetivo: {plan.target_rir_low}–{plan.target_rir_high}\n"
            f"- Notas: {plan.notes or '—'}\n"
            "\n## ESQUELETO DEL DÍA\n"
            f"{[t.model_dump() for t in structure.days_template]}\n"
            "\n## FASE Y SPLIT\n"
            f"phase={structure.phase} · split={structure.split_type} · "
            f"training_days_per_week={structure.training_days_per_week}\n"
            "\n## CATÁLOGO DE EJERCICIOS DISPONIBLES\n"
            f"{catalog_blob}\n"
            "\n## CONTEXTO RAG\n"
            f"{rag_context}\n"
            "\n## TAREA\n"
            "Devuelve un `Microcycle` con `training_days` rellenos según el "
            "esqueleto. Cada `ProgrammedExercise.exercise_id` DEBE existir en el "
            "catálogo y el equipamiento DEBE estar disponible. Aplica las reglas "
            "de progresión y técnicas del system prompt. Si es descarga, baja el "
            "volumen y sube el RIR.\n"
        )
        return await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_model=Microcycle,
            max_tokens=8192,
            thinking=True,
        )

    @staticmethod
    def _compact_catalog(db: ExerciseDatabase, available: list[Equipment]) -> str:
        """Renderiza el catálogo filtrado por equipamiento como lista compacta."""
        available_set: set[Equipment] = set(available)
        lines: list[str] = []
        for ex in db.exercises:
            if not set(ex.equipment).issubset(available_set):
                continue
            lines.append(_format_exercise_for_catalog(ex))
        return "\n".join(lines)


def _format_exercise_for_catalog(ex: Exercise) -> str:
    """Renderiza una sola entrada del catálogo en una línea para el LLM."""
    primary: str = ",".join(m.value for m in ex.primary_muscles)
    return (
        f"- {ex.id} · {ex.name} · pattern={ex.movement_pattern.value} · "
        f"primary={primary} · profile={ex.force_profile.value} · "
        f"compound={ex.is_compound} · default_reps={ex.default_rep_range}"
    )
