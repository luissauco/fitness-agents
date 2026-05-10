"""Agente de evaluación corporal.

Combina cálculo metabólico determinístico (Mifflin-St Jeor + IMC + fórmula Navy
opcional) con análisis visual de las 4 fotos del usuario por Claude Vision y
una recomendación de fase apoyada en el RAG.

El cálculo metabólico se delega en `MetabolicEstimates.from_basic_data` (modelo)
para que el agente solo orqueste; el agente añade la fórmula Navy para % graso
estimado cuando hay medidas suficientes.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import date
from typing import ClassVar, Final, Literal

from src.agents.base import BaseAgent
from src.agents.claude_client import image_block_from_path
from src.knowledge.retriever import AgentType
from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    MetabolicEstimates,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.user_profile import UserProfile
from src.models.validators import validate_macros_consistency

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Mapeo (NEAT, días entreno) → factor de actividad sobre BMR.
# Cubre el espectro habitual entre sedentario (1.2) y muy activo (1.9).
_ACTIVITY_FACTORS: Final[dict[tuple[str, str], float]] = {
    ("low", "low"): 1.375,  # 0-3 días
    ("low", "mid"): 1.55,  # 4-5 días
    ("low", "high"): 1.725,  # 6-7 días
    ("moderate", "low"): 1.5,
    ("moderate", "mid"): 1.65,
    ("moderate", "high"): 1.8,
    ("high", "low"): 1.7,
    ("high", "mid"): 1.85,
    ("high", "high"): 1.9,
}


def _training_bucket(days: int) -> Literal["low", "mid", "high"]:
    """Convierte días/semana de entreno en uno de los buckets del mapping."""
    if days <= 3:
        return "low"
    if days <= 5:
        return "mid"
    return "high"


def _navy_body_fat(
    *,
    sex: Literal["M", "F"],
    height_cm: float,
    waist_cm: float | None,
    neck_cm: float | None,
    hip_cm: float | None,
) -> float | None:
    """Estimación de % graso por la fórmula de la Marina de EE. UU. (variante métrica).

    Usa la formulación `495 / (denom) − 450` con los coeficientes oficiales para
    cm, evitando las conversiones a pulgadas que producen valores erróneos.
    Devuelve `None` si faltan medidas o el resultado cae fuera de (1, 60)%.
    """
    if waist_cm is None or neck_cm is None:
        return None
    if waist_cm <= neck_cm:
        return None
    try:
        log_height: float = math.log10(height_cm)
        if sex == "M":
            denom: float = 1.0324 - 0.19077 * math.log10(waist_cm - neck_cm) + 0.15456 * log_height
        else:
            if hip_cm is None:
                return None
            sum_wh: float = waist_cm + hip_cm - neck_cm
            if sum_wh <= 0:
                return None
            denom = 1.29579 - 0.35004 * math.log10(sum_wh) + 0.22100 * log_height
        if denom <= 0:
            return None
        bf: float = 495.0 / denom - 450.0
    except ValueError:
        return None
    if not 1 < bf < 60:
        return None
    return round(bf, 1)


# ----------------------------------------------------------------- AssessmentAgent


class AssessmentAgent(BaseAgent):
    """Genera `BodyAssessment` a partir de perfil + medidas + fotos."""

    name: ClassVar[str] = "assessment"
    agent_type: ClassVar[AgentType | None] = "assessment"

    @property
    def model(self) -> str:
        """Sonnet 4.6: vision capable y suficiente para análisis estándar."""
        return self.settings.MODEL_SONNET

    # ---------------------------------------------------------------- API pública

    async def run(  # type: ignore[override]
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
    ) -> BodyAssessment:
        """Pipeline completo: metabolismo + vision + fase recomendada."""
        metabolic: MetabolicEstimates = self._calculate_metabolic_estimates(profile, measurements)
        visual: VisualAssessment = await self._analyze_photos(profile, measurements)
        phase: PhaseRecommendation = await self._recommend_phase(
            profile, measurements, visual, metabolic
        )

        return BodyAssessment(
            id=uuid.uuid4().hex[:12],
            user_id=profile.id,
            date=date.today(),
            measurements=measurements,
            visual=visual,
            metabolic=metabolic,
            phase_recommendation=phase,
            photos_analyzed=list(profile.body_photo_paths),
        )

    # ------------------------------------------------------- Cálculo metabólico

    def _calculate_metabolic_estimates(
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
    ) -> MetabolicEstimates:
        """Calcula BMR, TDEE, IMC, ratio cintura/cadera y % graso (fórmula Navy)."""
        factor: float = self._derive_activity_factor(profile)
        bf_navy: float | None = _navy_body_fat(
            sex=profile.personal.sex,
            height_cm=profile.personal.height_cm,
            waist_cm=measurements.waist_cm,
            neck_cm=measurements.neck_cm,
            hip_cm=measurements.hip_cm,
        )
        return MetabolicEstimates.from_basic_data(
            weight_kg=measurements.weight_kg,
            height_cm=profile.personal.height_cm,
            age=profile.personal.age,
            sex=profile.personal.sex,
            activity_factor=factor,
            waist_cm=measurements.waist_cm,
            hip_cm=measurements.hip_cm,
            estimated_bf_formula=bf_navy,
        )

    @staticmethod
    def _derive_activity_factor(profile: UserProfile) -> float:
        """Mapea NEAT + días de entreno al multiplicador del BMR."""
        bucket: tuple[str, str] = (
            profile.activity.neat_level,
            _training_bucket(profile.activity.training_days_per_week),
        )
        return _ACTIVITY_FACTORS[bucket]

    # ------------------------------------------------------------- Vision call

    async def _analyze_photos(
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
    ) -> VisualAssessment:
        """Una llamada multimodal con las fotos disponibles → `VisualAssessment`."""
        photo_blocks: list[dict] = []
        for path in profile.body_photo_paths:
            try:
                photo_blocks.append(image_block_from_path(path))
            except FileNotFoundError as exc:
                _logger.warning(
                    "assessment.missing_photo",
                    extra={"user_id": profile.id, "path": str(path), "error": str(exc)},
                )

        intro: str = (
            f"Analiza la composición corporal de esta persona. "
            f"Datos: {profile.personal.sex}, {profile.personal.age} años, "
            f"{profile.personal.height_cm:.1f} cm, {measurements.weight_kg:.1f} kg. "
            f"Objetivo declarado: {profile.goals.primary_goal}. "
            "Devuelve `VisualAssessment` con rangos conservadores."
        )
        user_message: list[dict] = [{"type": "text", "text": intro}, *photo_blocks]

        return await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=user_message if photo_blocks else intro,
            response_model=VisualAssessment,
            max_tokens=2048,
            temperature=0.4,
        )

    # ----------------------------------------------------------- Recomendación

    async def _recommend_phase(
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
        visual: VisualAssessment,
        metabolic: MetabolicEstimates,
    ) -> PhaseRecommendation:
        """Recomienda fase consultando RAG y razonando sobre el conjunto de datos."""
        bf_lo, bf_hi = visual.estimated_body_fat_range
        rag_query: str = (
            f"recomendación de fase nutricional para objetivo {profile.goals.primary_goal} "
            f"con % graso {bf_lo:.0f}-{bf_hi:.0f}% y experiencia "
            f"{profile.activity.current_training_type or 'desconocida'}"
        )
        rag_context: str = await self.get_rag_context(rag_query, k=5)

        prompt: str = self._build_phase_prompt(
            profile, measurements, visual, metabolic, rag_context
        )
        recommendation: PhaseRecommendation = await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_model=PhaseRecommendation,
            max_tokens=2048,
            temperature=0.4,
        )

        if not validate_macros_consistency(recommendation.suggested_macros):
            _logger.warning(
                "assessment.macros_inconsistent",
                extra={
                    "user_id": profile.id,
                    "macros": recommendation.suggested_macros.model_dump(),
                },
            )
        return recommendation

    @staticmethod
    def _build_phase_prompt(
        profile: UserProfile,
        measurements: BodyMeasurements,
        visual: VisualAssessment,
        metabolic: MetabolicEstimates,
        rag_context: str,
    ) -> str:
        """Compone el user message para la llamada de recomendación de fase."""
        return (
            "## DATOS DEL USUARIO\n"
            f"- Sexo: {profile.personal.sex} · Edad: {profile.personal.age}\n"
            f"- Peso: {measurements.weight_kg} kg · Altura: {profile.personal.height_cm} cm\n"
            f"- Objetivo principal: {profile.goals.primary_goal}\n"
            f"- Detalle objetivo: {profile.goals.primary_goal_detail}\n"
            f"- Días entreno/semana: {profile.activity.training_days_per_week} · "
            f"NEAT: {profile.activity.neat_level}\n"
            f"- Tipo de entreno previo: {profile.activity.current_training_type or '—'}\n"
            f"- Lesiones: {profile.activity.injuries or '—'}\n"
            "\n## METABOLISMO ESTIMADO\n"
            f"- BMR: {metabolic.bmr} kcal · TDEE: {metabolic.tdee} kcal "
            f"(factor {metabolic.activity_factor})\n"
            f"- IMC: {metabolic.bmi} · WHR: {metabolic.waist_hip_ratio or '—'}\n"
            f"- % graso fórmula Navy: {metabolic.estimated_bf_formula or '—'}\n"
            "\n## LECTURA VISUAL\n"
            f"- Rango % graso: {visual.estimated_body_fat_range[0]}–"
            f"{visual.estimated_body_fat_range[1]}%\n"
            f"- Distribución: {visual.fat_distribution}\n"
            f"- Puntos fuertes: {visual.strong_points}\n"
            f"- Puntos débiles: {visual.weak_points}\n"
            f"- Impresión general: {visual.overall_impression}\n"
            "\n## CONOCIMIENTO RECUPERADO (RAG)\n"
            f"{rag_context}\n"
            "\n## TAREA\n"
            "Devuelve `PhaseRecommendation` aplicando las reglas duras del system "
            "prompt. Cita en `reasoning` los chunks del RAG por título."
        )
