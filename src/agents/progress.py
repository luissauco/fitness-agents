"""Agente de análisis bisemanal de progreso.

Combina cálculos determinísticos (tendencia de peso, agregados de entreno) con
una llamada a Claude (vision si hay fotos nuevas) para razonar la decisión de
ajuste para el siguiente periodo.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Any, ClassVar, Final

from src.agents.base import BaseAgent
from src.agents.claude_client import image_block_from_path
from src.knowledge.retriever import AgentType
from src.models.checkin_input import CheckinInput
from src.models.mesocycle import Mesocycle
from src.models.nutrition_plan import NutritionPlan
from src.models.progress_log import (
    NutritionAdherence,
    PhotoComparison,
    ProgressDecision,
    ProgressLog,
    SubjectiveFeedback,
    TrainingProgress,
    WeightLog,
)
from src.models.user_profile import UserProfile

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Umbrales para reglas duras de decisión.
_LOW_ENERGY_THRESHOLD: Final[int] = 4
_HIGH_SORENESS_THRESHOLD: Final[int] = 7
_LOW_ADHERENCE_THRESHOLD: Final[float] = 0.7
_PERIOD_DAYS: Final[int] = 14


# ----------------------------------------------------------------- ProgressAgent


class ProgressAgent(BaseAgent):
    """Analiza el periodo y produce un `ProgressLog` con decisión justificada."""

    name: ClassVar[str] = "progress"
    agent_type: ClassVar[AgentType | None] = "progress"

    @property
    def model(self) -> str:
        """Sonnet 4.6 con vision para comparar fotos antes/después."""
        return self.settings.MODEL_SONNET

    # ------------------------------------------------------------------- API

    async def run(  # type: ignore[override]
        self,
        profile: UserProfile,
        current_mesocycle: Mesocycle,
        current_plan: NutritionPlan,
        checkin_data: CheckinInput,
        previous_logs: list[ProgressLog],
        microcycle_completed: int | None = None,
    ) -> ProgressLog:
        """Pipeline completo: tendencias + (vision) + decisión."""
        completed_micro: int = (
            microcycle_completed
            if microcycle_completed is not None
            else self._infer_microcycle_completed(current_mesocycle, previous_logs)
        )

        weight: WeightLog = self._analyze_weight_trend(checkin_data.weights, previous_logs)
        training: TrainingProgress = self._analyze_training_progress(
            current_mesocycle, completed_micro, checkin_data
        )
        nutrition: NutritionAdherence = self._summarize_nutrition_adherence(checkin_data)

        photos: PhotoComparison | None = None
        if checkin_data.photos:
            photos = await self._compare_photos(
                current_photos=checkin_data.photos,
                previous_photos=self._previous_photos(profile, previous_logs),
            )

        decision: ProgressDecision = await self._make_decision(
            profile=profile,
            current_mesocycle=current_mesocycle,
            current_plan=current_plan,
            weight=weight,
            training=training,
            nutrition=nutrition,
            subjective=checkin_data.subjective,
            photos=photos,
            previous_logs=previous_logs,
            microcycle_completed=completed_micro,
        )

        period_end: date = date.today()
        period_start: date = period_end - timedelta(days=_PERIOD_DAYS)
        return ProgressLog(
            id=uuid.uuid4().hex[:12],
            user_id=profile.id,
            mesocycle_id=current_mesocycle.id,
            microcycle_number=completed_micro,
            date=period_end,
            period_start=period_start,
            period_end=period_end,
            weight=weight,
            measurements=checkin_data.measurements,
            training=training,
            nutrition=nutrition,
            subjective=checkin_data.subjective,
            photos=photos,
            daily_steps_avg=checkin_data.daily_steps_avg,
            decision=decision,
            report_summary=self._fallback_summary(weight, training, decision),
        )

    # ------------------------------------------------ Análisis determinístico

    @staticmethod
    def _analyze_weight_trend(
        weights: list[float], previous_logs: list[ProgressLog]
    ) -> WeightLog:
        """Construye `WeightLog` con tendencia frente a la última media registrada."""
        last_average: float | None = (
            previous_logs[-1].weight.average if previous_logs else None
        )
        return WeightLog.from_weights(weights, last_average=last_average)

    @staticmethod
    def _analyze_training_progress(
        current_mesocycle: Mesocycle,
        microcycle_completed: int,
        checkin_data: CheckinInput,
    ) -> TrainingProgress:
        """Compara los logs del periodo con los del microciclo previo."""
        if not current_mesocycle.microcycles:
            return TrainingProgress(
                exercises_tracked=0,
                exercises_progressed=0,
                exercises_stagnated=0,
                exercises_regressed=0,
                volume_adherence_pct=0.0,
            )

        # Mapa exercise_id → max kg movido en el periodo actual.
        current_max: dict[str, float] = {}
        for log in checkin_data.training_logs:
            ex_id: str = str(log.get("exercise_id", ""))
            if not ex_id:
                continue
            kgs: list[float] = [
                float(s.get("weight_kg", 0)) for s in log.get("sets", []) if "weight_kg" in s
            ]
            if kgs:
                current_max[ex_id] = max(kgs)

        # Mapa exercise_id → max kg en el microciclo anterior (logs previos).
        previous_max: dict[str, float] = {}
        prev_idx: int = max(microcycle_completed - 2, 0)
        if prev_idx < len(current_mesocycle.microcycles):
            previous_micro = current_mesocycle.microcycles[prev_idx]
            for d in previous_micro.training_days:
                for pe in d.exercises:
                    log = pe.logs.get(prev_idx + 1)
                    if log is None:
                        continue
                    kgs = [
                        float(s.get("weight_kg", 0)) for s in log.sets if "weight_kg" in s
                    ]
                    if kgs:
                        previous_max[pe.exercise_id] = max(kgs)

        progressed: int = 0
        stagnated: int = 0
        regressed: int = 0
        problem_exercises: list[str] = []
        for ex_id, kg_now in current_max.items():
            kg_prev: float | None = previous_max.get(ex_id)
            if kg_prev is None:
                continue
            if kg_now > kg_prev:
                progressed += 1
            elif kg_now < kg_prev:
                regressed += 1
                problem_exercises.append(ex_id)
            else:
                stagnated += 1

        tracked: int = len(current_max)
        # Si no hay base previa, asumimos volumen completo (100 %).
        adherence_pct: float = (
            100.0 if tracked == 0 else min(100.0, 100.0 * tracked / max(1, len(current_max)))
        )

        return TrainingProgress(
            exercises_tracked=tracked,
            exercises_progressed=progressed,
            exercises_stagnated=stagnated,
            exercises_regressed=regressed,
            volume_adherence_pct=round(adherence_pct, 1),
            problem_exercises=problem_exercises,
        )

    @staticmethod
    def _summarize_nutrition_adherence(checkin: CheckinInput) -> NutritionAdherence:
        """Resumen de adherencia nutricional a partir de los datos auto-reportados."""
        return NutritionAdherence(
            adherence_pct=round(100.0 * checkin.nutrition_adherence_self_estimate, 1),
            cheat_meals_count=checkin.cheat_meals_count,
            missed_meals_avg=0.0,
            supplement_adherence=True,
            water_intake_liters=0.0,
        )

    @staticmethod
    def _previous_photos(
        profile: UserProfile, previous_logs: list[ProgressLog]
    ) -> list[str]:
        """Devuelve las fotos del último log o, en su defecto, las del onboarding."""
        for log in reversed(previous_logs):
            if log.photos and log.photos.current_photos:
                return list(log.photos.current_photos)
        return list(profile.body_photo_paths)

    @staticmethod
    def _infer_microcycle_completed(
        mesocycle: Mesocycle, previous_logs: list[ProgressLog]
    ) -> int:
        """Si no se pasa explícito, asume que es el siguiente microciclo no logeado."""
        logs_for_meso: list[ProgressLog] = [
            log for log in previous_logs if log.mesocycle_id == mesocycle.id
        ]
        # 1-indexed.
        next_micro: int = len(logs_for_meso) + 1
        return min(next_micro, len(mesocycle.microcycles))

    # ------------------------------------------------------------- Vision call

    async def _compare_photos(
        self,
        *,
        current_photos: list[str],
        previous_photos: list[str],
    ) -> PhotoComparison:
        """Llamada multimodal con fotos actuales + previas → `PhotoComparison`."""
        blocks: list[dict[str, Any]] = [
            {"type": "text", "text": "Fotos previas:"}
        ]
        for path in previous_photos:
            try:
                blocks.append(image_block_from_path(path))
            except FileNotFoundError as exc:
                _logger.warning("progress.previous_photo_missing", extra={"err": str(exc)})
        blocks.append({"type": "text", "text": "Fotos actuales:"})
        for path in current_photos:
            try:
                blocks.append(image_block_from_path(path))
            except FileNotFoundError as exc:
                _logger.warning("progress.current_photo_missing", extra={"err": str(exc)})
        blocks.append(
            {
                "type": "text",
                "text": (
                    "Devuelve `PhotoComparison`: identifica cambios visibles, "
                    "zonas mejoradas y zonas sin cambio. Sé conservador."
                ),
            }
        )

        comparison: PhotoComparison = await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=blocks,
            response_model=PhotoComparison,
            max_tokens=2048,
            temperature=0.4,
        )
        # Forzamos coherencia: la lista de current_photos es la del checkin.
        comparison.current_photos = list(current_photos)
        comparison.previous_photos = list(previous_photos)
        return comparison

    # -------------------------------------------------------- Decisión (LLM)

    async def _make_decision(
        self,
        *,
        profile: UserProfile,
        current_mesocycle: Mesocycle,
        current_plan: NutritionPlan,
        weight: WeightLog,
        training: TrainingProgress,
        nutrition: NutritionAdherence,
        subjective: SubjectiveFeedback,
        photos: PhotoComparison | None,
        previous_logs: list[ProgressLog],
        microcycle_completed: int,
    ) -> ProgressDecision:
        """Llama al LLM (con RAG) para tomar la decisión de ajuste."""
        # Heurísticas duras antes del LLM (por si la API falla y para guiar el prompt).
        forced_decision: str | None = self._forced_decision(
            current_mesocycle, microcycle_completed, subjective, previous_logs
        )

        rag_context: str = await self.get_rag_context(
            f"ajuste de plan en fase {current_plan.phase} con tendencia "
            f"{weight.trend} y adherencia {nutrition.adherence_pct}%",
            k=4,
        )
        prompt: str = self._build_decision_prompt(
            profile=profile,
            current_mesocycle=current_mesocycle,
            current_plan=current_plan,
            weight=weight,
            training=training,
            nutrition=nutrition,
            subjective=subjective,
            photos=photos,
            previous_logs=previous_logs,
            microcycle_completed=microcycle_completed,
            forced_decision=forced_decision,
            rag_context=rag_context,
        )
        return await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_model=ProgressDecision,
            max_tokens=2048,
            temperature=0.4,
        )

    @staticmethod
    def _forced_decision(
        current_mesocycle: Mesocycle,
        microcycle_completed: int,
        subjective: SubjectiveFeedback,
        previous_logs: list[ProgressLog],
    ) -> str | None:
        """Devuelve la acción forzada por reglas duras, si aplica."""
        if microcycle_completed >= len(current_mesocycle.microcycles):
            return "new_mesocycle"
        # Fatiga sostenida en 2 periodos consecutivos.
        is_fatigued_now: bool = (
            subjective.energy_level < _LOW_ENERGY_THRESHOLD
            and subjective.soreness > _HIGH_SORENESS_THRESHOLD
        )
        if is_fatigued_now and previous_logs:
            prev = previous_logs[-1].subjective
            if (
                prev.energy_level < _LOW_ENERGY_THRESHOLD
                and prev.soreness > _HIGH_SORENESS_THRESHOLD
            ):
                return "early_deload"
        return None

    @staticmethod
    def _build_decision_prompt(
        *,
        profile: UserProfile,
        current_mesocycle: Mesocycle,
        current_plan: NutritionPlan,
        weight: WeightLog,
        training: TrainingProgress,
        nutrition: NutritionAdherence,
        subjective: SubjectiveFeedback,
        photos: PhotoComparison | None,
        previous_logs: list[ProgressLog],
        microcycle_completed: int,
        forced_decision: str | None,
        rag_context: str,
    ) -> str:
        """Compone el user message para la llamada de decisión."""
        photo_block: str = (
            f"- Cambios: {photos.visual_changes}\n- Mejoras: {photos.areas_improved}\n"
            if photos
            else "(sin comparativa de fotos)\n"
        )
        last_three = [log.decision.action for log in previous_logs[-3:]] if previous_logs else []
        forced_hint: str = (
            f"\n## REGLA DURA APLICABLE\n`action` debe ser `{forced_decision}`. "
            "Justifica ese ajuste con los datos del periodo.\n"
            if forced_decision
            else ""
        )
        return (
            "## CONTEXTO\n"
            f"- Fase nutricional: {current_plan.phase}\n"
            f"- Mesociclo: {current_mesocycle.name} · "
            f"micro completado: {microcycle_completed}/{len(current_mesocycle.microcycles)}\n"
            f"- Decisiones de los últimos periodos: {last_three}\n"
            "\n## PESO\n"
            f"- Media periodo: {weight.average} kg · trend: {weight.trend} · "
            f"cambio respecto al anterior: {weight.change_from_last} kg\n"
            "\n## ENTRENAMIENTO\n"
            f"- Trackeados: {training.exercises_tracked} · "
            f"progresados: {training.exercises_progressed} · "
            f"estancados: {training.exercises_stagnated} · "
            f"regresados: {training.exercises_regressed}\n"
            f"- Adherencia volumen: {training.volume_adherence_pct}%\n"
            f"- Ejercicios problemáticos: {training.problem_exercises}\n"
            "\n## NUTRICIÓN\n"
            f"- Adherencia auto-reportada: {nutrition.adherence_pct}%\n"
            f"- Cheat meals: {nutrition.cheat_meals_count}\n"
            "\n## SENSACIONES\n"
            f"- Energía: {subjective.energy_level}/10 · "
            f"sueño: {subjective.sleep_quality}/10 · "
            f"DOMS: {subjective.soreness}/10 · "
            f"hambre: {subjective.hunger_level}/10 · "
            f"motivación: {subjective.motivation}/10\n"
            f"- Dolor o molestia: {subjective.pain_or_discomfort or '—'}\n"
            "\n## FOTOS\n"
            f"{photo_block}"
            "\n## RAG\n"
            f"{rag_context}\n"
            f"{forced_hint}"
            "\n## TAREA\n"
            "Devuelve `ProgressDecision` con `action`, `reasoning` (3–5 líneas) y "
            "`details` con los números clave del ajuste (calorie_change, "
            "volume_change, etc.). Aplica las reglas duras del system prompt."
        )

    # ------------------------------------------------------------- Resumen

    @staticmethod
    def _fallback_summary(
        weight: WeightLog,
        training: TrainingProgress,
        decision: ProgressDecision,
    ) -> str:
        """Resumen objetivo de respaldo (la decisión del LLM puede traer otro)."""
        return (
            f"Peso medio {weight.average} kg ({weight.trend}). "
            f"Entreno: {training.exercises_progressed} progresados, "
            f"{training.exercises_stagnated} estancados, "
            f"{training.exercises_regressed} regresados. "
            f"Decisión: {decision.action}. Razonamiento: {decision.reasoning[:200]}"
        )
