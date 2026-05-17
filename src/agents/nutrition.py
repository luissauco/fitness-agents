"""Agente generador del plan nutricional.

El cálculo de macros objetivo es determinístico (TDEE × factor de fase, con
proteína 2 g/kg, grasa 0.9 g/kg, HC en lo que reste). El LLM solo se encarga
de cuadrar las comidas reales con esos macros y respetar gustos/alergias.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import ClassVar, Final, Literal

from src.agents.base import BaseAgent
from src.knowledge.retriever import AgentType
from src.models.body_assessment import BodyAssessment
from src.models.common import MacroDistribution
from src.models.mesocycle import Mesocycle
from src.models.nutrition_plan import (
    CheatMealProtocol,
    DailyDiet,
    GeneralTips,
    InterchangeRules,
    NutritionPlan,
)
from src.models.user_profile import UserProfile
from src.models.validators import validate_macros_consistency

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Factor sobre TDEE según fase nutricional recomendada.
_PHASE_FACTORS: Final[dict[str, float]] = {
    "minicut": -0.25,
    "cut": -0.175,
    "maintenance": 0.0,
    "recomposition": 0.0,
    "lean_bulk": 0.10,
    "bulk": 0.175,
}

# Recorte de kcal del día de descanso respecto al de entreno (los HC bajan).
_REST_DAY_KCAL_DELTA: Final[int] = 300

# Mínimos hormonales/funcionales por kg.
_PROTEIN_PER_KG: Final[float] = 2.0
_FAT_PER_KG: Final[float] = 0.9
_PROTEIN_MIN_PER_KG: Final[float] = 1.6
_FAT_MIN_PER_KG: Final[float] = 0.6


# ----------------------------------------------------------------- NutritionAgent


class NutritionAgent(BaseAgent):
    """Genera `NutritionPlan` coherente con la fase recomendada y el perfil."""

    name: ClassVar[str] = "nutrition"
    agent_type: ClassVar[AgentType | None] = "nutrition"

    @property
    def model(self) -> str:
        """Opus 4.7: cuadrar macros + intercambiabilidad + restricciones es complejo."""
        return self.settings.MODEL_OPUS

    # ------------------------------------------------------------------- API

    async def run(  # type: ignore[override]
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        mesocycle: Mesocycle,
        previous_plan: NutritionPlan | None = None,
    ) -> NutritionPlan:
        """Genera el plan completo: dieta de entreno + descanso + reglas globales."""
        train_target: MacroDistribution = self._calculate_target_macros(
            profile, assessment, day_type="training"
        )
        rest_target: MacroDistribution = self._calculate_target_macros(
            profile, assessment, day_type="rest"
        )
        self._enforce_minimums(profile, train_target)
        self._enforce_minimums(profile, rest_target)

        rag_context: str = await self._gather_rag_context(profile, assessment)
        train_diet: DailyDiet = await self._design_meals(
            target_macros=train_target,
            profile=profile,
            day_type="training",
            mesocycle=mesocycle,
            rag_context=rag_context,
        )
        rest_diet: DailyDiet = await self._design_meals(
            target_macros=rest_target,
            profile=profile,
            day_type="rest",
            mesocycle=mesocycle,
            rag_context=rag_context,
        )

        return NutritionPlan(
            id=uuid.uuid4().hex[:12],
            user_id=profile.id,
            name=self._plan_name(assessment),
            objective=profile.goals.primary_goal_detail or profile.goals.primary_goal,
            phase=assessment.phase_recommendation.recommended_phase,
            duration=f"{assessment.phase_recommendation.suggested_duration_weeks} semanas",
            start_date=date.today(),
            training_day_diet=train_diet,
            rest_day_diet=rest_diet,
            interchange_rules=self._build_interchange_rules(),
            cheat_meal_protocol=self._build_cheat_meal_protocol(
                assessment.phase_recommendation.recommended_phase
            ),
            general_tips=self._build_general_tips(),
            neat_cardio_notes=self._build_neat_notes(
                assessment.phase_recommendation.recommended_phase
            ),
        )

    # ------------------------------------------------------ Cálculo determinístico

    def _calculate_target_macros(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        day_type: Literal["training", "rest"],
    ) -> MacroDistribution:
        """Calcula los macros objetivo según fase y tipo de día."""
        tdee: float = assessment.metabolic.tdee
        phase: str = assessment.phase_recommendation.recommended_phase
        factor: float = _PHASE_FACTORS.get(phase, 0.0)
        kcal_target: int = max(int(round(tdee * (1 + factor))), int(assessment.metabolic.bmr))
        if day_type == "rest":
            kcal_target = max(kcal_target - _REST_DAY_KCAL_DELTA, int(assessment.metabolic.bmr))

        weight_kg: float = profile.personal.weight_kg
        protein_g: int = int(round(_PROTEIN_PER_KG * weight_kg))
        fat_g: int = int(round(_FAT_PER_KG * weight_kg))
        kcal_minus_pf: int = kcal_target - protein_g * 4 - fat_g * 9
        carbs_g: int = max(0, int(round(kcal_minus_pf / 4)))

        # Reajusta calories al total real para que validate_macros_consistency pase.
        actual_kcal: int = protein_g * 4 + carbs_g * 4 + fat_g * 9
        return MacroDistribution(
            calories=actual_kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g
        )

    @staticmethod
    def _enforce_minimums(profile: UserProfile, macros: MacroDistribution) -> None:
        """Verifica las reglas duras de mínimos hormonales y proteicos."""
        weight_kg: float = profile.personal.weight_kg
        if macros.protein_g < _PROTEIN_MIN_PER_KG * weight_kg:
            raise ValueError(
                f"Proteína {macros.protein_g} g < mínimo {_PROTEIN_MIN_PER_KG}×{weight_kg} kg."
            )
        if macros.fat_g < _FAT_MIN_PER_KG * weight_kg:
            raise ValueError(f"Grasas {macros.fat_g} g < mínimo {_FAT_MIN_PER_KG}×{weight_kg} kg.")
        if not validate_macros_consistency(macros):
            raise ValueError("Macros no consistentes con kcal totales (>50 kcal de error).")

    # ------------------------------------------------------------------ Constantes

    @staticmethod
    def _build_interchange_rules() -> InterchangeRules:
        """Reglas de intercambio canónicas del sistema (no dependen del usuario)."""
        return InterchangeRules(
            carb_sources={
                "100g arroz cocido": "100g pasta cocida / 100g quinoa cocida / "
                "100g cous-cous cocido / 100g legumbres cocidas / "
                "450g patata cocida / 450g boniato cocido",
            },
            protein_sources=[
                "pollo",
                "pavo",
                "pescado blanco",
                "burger meat magra",
                "lomo de cerdo magro",
            ],
            vegetable_rule=(
                "Verduras intercambiables a igualdad de gramos. Mínimo 200 g/día "
                "repartidos entre comida y cena."
            ),
            fruit_rule=(
                "Frutas intercambiables a igualdad de gramos EXCEPTO plátano "
                "(contar como hidratos: 1 plátano ≈ 30 g HC)."
            ),
            notes=[
                "Las cantidades son siempre en cocido salvo indicación contraria.",
                "Las salsas y especias se permiten siempre que sumen 0 kcal.",
            ],
        )

    @staticmethod
    def _build_cheat_meal_protocol(phase: str) -> CheatMealProtocol:
        """Protocolo de comida libre adaptado a la fase."""
        if phase in ("minicut", "cut"):
            frequency: str = "1 comida cada 14 días"
        elif phase in ("lean_bulk", "bulk"):
            frequency = "no es necesaria; si hay evento social, sin culpa"
        else:
            frequency = "1 comida cada 10–14 días"
        return CheatMealProtocol(
            strategy=(
                "Cheat meal en una sola comida, no día completo. Idealmente "
                "post-entreno para aprovechar el flujo de glucógeno."
            ),
            pre_cheat_tips=[
                "Mantén proteína del día como cualquier otro.",
                "Bebe agua antes para no comer por sed.",
            ],
            day_structure=[
                "Mañana: comida normal del plan.",
                "Mediodía: comida normal del plan.",
                "Tarde: entreno habitual.",
                "Cena: cheat meal libre, dentro de un margen razonable.",
            ],
            frequency=frequency,
        )

    @staticmethod
    def _build_general_tips() -> GeneralTips:
        """Consejos generales y reglas globales aplicables siempre."""
        return GeneralTips(
            tips=[
                "Pesa los alimentos en cocido cuando sea posible.",
                "Mantén una hidratación de 30–40 ml/kg de peso corporal.",
                "La adherencia gana a la perfección: 80 % bien hecho durante 12 "
                "semanas vence al 100 % perfecto durante 2.",
            ],
            allowed_drinks=["agua", "café sin azúcar", "té / infusiones", "refrescos zero"],
            sauce_rule="Salsas y aliños permitidos siempre que sumen 0 kcal.",
            seasoning_notes=(
                "Especias, hierbas, vinagre, mostaza, salsa de soja baja en sodio: libres."
            ),
        )

    @staticmethod
    def _build_neat_notes(phase: str) -> str:
        """Pautas de NEAT y cardio coherentes con la fase."""
        if phase in ("minicut", "cut"):
            return (
                "10 500 pasos en días de entreno y 12 500 en descanso. "
                "Opcionalmente 1–2 sesiones de LISS de 25–30 min."
            )
        if phase in ("lean_bulk", "bulk"):
            return (
                "9 500 pasos en entreno y 11 000 en descanso. "
                "Cardio LISS opcional 1×/semana para salud cardiovascular."
            )
        return "10 000 pasos en entreno y 12 000 en descanso."

    @staticmethod
    def _plan_name(assessment: BodyAssessment) -> str:
        """Nombre legible del plan (ej. 'Plan Lean Bulk · 12 semanas')."""
        phase: str = assessment.phase_recommendation.recommended_phase
        weeks: int = assessment.phase_recommendation.suggested_duration_weeks
        return f"Plan {phase.replace('_', ' ').title()} · {weeks} semanas"

    # --------------------------------------------------------------------- RAG

    async def _gather_rag_context(self, profile: UserProfile, assessment: BodyAssessment) -> str:
        """Une consultas relevantes al RAG en un único bloque."""
        phase: str = assessment.phase_recommendation.recommended_phase
        queries: list[str] = [
            f"estructura de comidas y reparto de macros en fase {phase}",
            f"alimentos prácticos y intercambiables en {phase} con "
            f"{profile.nutrition.meals_per_day} comidas/día",
        ]
        chunks: list[str] = []
        for q in queries:
            chunks.append(await self.get_rag_context(q, k=3))
        return "\n\n---\n\n".join(c for c in chunks if c)

    # ------------------------------------------------------------- LLM: comidas

    async def _design_meals(
        self,
        *,
        target_macros: MacroDistribution,
        profile: UserProfile,
        day_type: Literal["training", "rest"],
        mesocycle: Mesocycle,
        rag_context: str,
    ) -> DailyDiet:
        """Pide al LLM una `DailyDiet` que cuadre los macros del día."""
        prompt: str = self._build_meals_prompt(
            target_macros=target_macros,
            profile=profile,
            day_type=day_type,
            mesocycle=mesocycle,
            rag_context=rag_context,
        )
        diet: DailyDiet = await self.claude.generate_structured(
            model=self.model,
            system_prompt=self.system_prompt,
            user_message=prompt,
            response_model=DailyDiet,
            max_tokens=8192,
            temperature=0.5,
            thinking=True,
        )
        if diet.day_type != day_type:
            _logger.warning(
                "nutrition.day_type_mismatch",
                extra={"expected": day_type, "got": diet.day_type, "user_id": profile.id},
            )
            diet.day_type = day_type
        return diet

    @staticmethod
    def _build_meals_prompt(
        *,
        target_macros: MacroDistribution,
        profile: UserProfile,
        day_type: Literal["training", "rest"],
        mesocycle: Mesocycle,
        rag_context: str,
    ) -> str:
        """Compone el user message para la llamada de diseño de comidas."""
        nutri = profile.nutrition
        return (
            f"## DÍA A DISEÑAR\n- day_type: {day_type}\n"
            f"- Mesociclo asociado: {mesocycle.name} (split {mesocycle.split_type}, "
            f"fase {mesocycle.phase})\n"
            f"\n## TARGET MACROS\n"
            f"- calories: {target_macros.calories}\n"
            f"- protein_g: {target_macros.protein_g}\n"
            f"- carbs_g: {target_macros.carbs_g}\n"
            f"- fat_g: {target_macros.fat_g}\n"
            f"\n## PERFIL\n"
            f"- Peso: {profile.personal.weight_kg} kg · "
            f"Altura: {profile.personal.height_cm} cm\n"
            f"- meals_per_day: {nutri.meals_per_day}\n"
            f"- training_time: {profile.activity.training_time}\n"
            f"- alimentos habituales: {nutri.typical_foods}\n"
            f"- gustos cómodos: {nutri.comfortable_food_groups or '—'}\n"
            f"- no le gustan: {nutri.disliked_foods or '—'}\n"
            f"- ALERGIAS: {nutri.allergies or '—'}\n"
            f"- INTOLERANCIAS: {nutri.intolerances or '—'}\n"
            f"- abierto a suplementos: {nutri.open_to_supplements}\n"
            f"- saltar desayuno: {nutri.open_to_skip_breakfast}\n"
            f"- ventana horaria reducida: {nutri.open_to_reduced_window}\n"
            f"\n## RAG\n{rag_context}\n"
            "\n## TAREA\n"
            "Devuelve un `DailyDiet` con `day_type` igual al solicitado. La suma "
            "de los macros de los `FoodItem` (asumiendo composición típica) debe "
            "estar a ±5 % del target. Cada FoodItem de HC o proteína debe llevar "
            "al menos 1 alternativa coherente con las reglas del system prompt."
        )
