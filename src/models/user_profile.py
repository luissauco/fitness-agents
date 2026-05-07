"""Perfil completo del usuario tras completar el cuestionario inicial.

Agrupa datos personales, perfil de actividad, perfil nutricional, objetivos y
equipamiento. `UserProfile.from_questionnaire(responses)` construye el perfil a
partir de las respuestas del cuestionario predeterminado.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.common import MacroDistribution
from src.models.exercise_db import Equipment
from src.models.questionnaire import QuestionnaireResponse


class PersonalData(BaseModel):
    """Datos personales y horarios habituales."""

    name: str
    age: int = Field(..., ge=10, le=100)
    sex: Literal["M", "F"]
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    wake_time: time
    sleep_time: time


class ActivityProfile(BaseModel):
    """Perfil de actividad física y entrenamiento previo."""

    training_days_per_week: int = Field(..., ge=0, le=7)
    rest_days_per_week: int = Field(..., ge=0, le=7)
    current_training_type: str | None = Field(
        default=None, description="Descripción del entrenamiento que viene siguiendo."
    )
    training_time: time | None = Field(default=None, description="Hora habitual de entreno.")
    neat_level: Literal["low", "moderate", "high"]
    injuries: list[str] = Field(default_factory=list)


class NutritionProfile(BaseModel):
    """Perfil nutricional actual y disposición a cambios."""

    current_calories: int | None = Field(default=None, ge=0)
    current_macros: MacroDistribution | None = None
    meals_per_day: int = Field(..., ge=1, le=10)
    typical_foods: str = Field(..., description="Descripción libre de su dieta habitual.")
    disliked_foods: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    intolerances: list[str] = Field(default_factory=list)
    salt_usage: Literal["low", "moderate", "high"]
    daily_water_liters: float = Field(..., ge=0)
    habitual_drinks: list[str] = Field(default_factory=list)
    comfortable_food_groups: list[str] = Field(default_factory=list)
    uncomfortable_food_groups: list[str] = Field(default_factory=list)
    open_to_supplements: bool = False
    open_to_fasting: bool = False
    open_to_skip_breakfast: bool = False
    open_to_reduced_window: bool = False


class Goals(BaseModel):
    """Objetivos del usuario."""

    primary_goal: Literal[
        "fat_loss", "muscle_gain", "recomposition", "minicut", "lean_bulk", "maintenance"
    ]
    primary_goal_detail: str
    secondary_goals: list[str] = Field(default_factory=list)
    target_timeframe: str | None = None
    priority_body_areas: list[str] = Field(default_factory=list)


class GymEquipment(BaseModel):
    """Equipamiento disponible en el gimnasio del usuario."""

    available_equipment: list[Equipment] = Field(default_factory=list)
    equipment_notes: str | None = None
    equipment_photo_paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------- Helpers de mapeo

# Normalización de valores SELECT del cuestionario al enum interno.
_NEAT_MAP: dict[str, Literal["low", "moderate", "high"]] = {
    "bajo": "low",
    "moderado": "moderate",
    "alto": "high",
}
_SALT_MAP: dict[str, Literal["low", "moderate", "high"]] = {
    "baja": "low",
    "moderada": "moderate",
    "alta": "high",
}


def _index(responses: list[QuestionnaireResponse]) -> dict[str, QuestionnaireResponse]:
    """Indexa las respuestas por id de pregunta (última respuesta gana)."""
    return {r.question_id: r for r in responses}


def _value(idx: dict[str, QuestionnaireResponse], qid: str, default: Any = None) -> Any:
    """Devuelve el value de una respuesta o `default` si no existe / está vacío."""
    r: QuestionnaireResponse | None = idx.get(qid)
    if r is None or r.value is None:
        return default
    return r.value


def _bool(idx: dict[str, QuestionnaireResponse], qid: str) -> bool:
    """Coerciona la respuesta de YES_NO a bool. Acepta int/str/bool."""
    v: Any = _value(idx, qid, default=False)
    if isinstance(v, bool):
        return v
    if isinstance(v, int | float):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"sí", "si", "yes", "true", "1"}
    return False


def _time(idx: dict[str, QuestionnaireResponse], qid: str) -> time | None:
    """Parsea respuesta TIME (formato HH:MM o HH:MM:SS) a `datetime.time`."""
    v: Any = _value(idx, qid)
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, str):
        return time.fromisoformat(v)
    raise TypeError(f"No se puede interpretar como time: {v!r}")


def _split_csv(value: Any) -> list[str]:
    """Convierte un valor en una lista de strings limpios. Acepta str (CSV) o list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return [str(value).strip()]


# ------------------------------------------------------------- UserProfile


class UserProfile(BaseModel):
    """Perfil completo del usuario."""

    id: str = Field(..., description="Identificador único del usuario.")
    created_at: datetime
    updated_at: datetime
    personal: PersonalData
    activity: ActivityProfile
    nutrition: NutritionProfile
    goals: Goals
    gym: GymEquipment
    body_photo_paths: list[str] = Field(
        default_factory=list,
        description="Frente, espalda, perfil izquierdo, perfil derecho.",
    )

    # ----------------------------------------------------- Construcción

    @classmethod
    def from_questionnaire(
        cls,
        responses: list[QuestionnaireResponse],
        *,
        user_id: str | None = None,
    ) -> UserProfile:
        """Construye el perfil a partir de respuestas al cuestionario predeterminado.

        Solo mapea los campos del cuestionario default (`Questionnaire.get_default()`).
        Los campos opcionales sin respuesta toman valores por defecto sensatos.
        """
        idx: dict[str, QuestionnaireResponse] = _index(responses)
        now: datetime = datetime.now()

        personal: PersonalData = PersonalData(
            name=_value(idx, "nombre"),
            age=int(_value(idx, "edad")),
            sex=_value(idx, "sexo"),
            height_cm=float(_value(idx, "altura_cm")),
            weight_kg=float(_value(idx, "peso_ayunas_kg")),
            wake_time=_time(idx, "hora_levantarse"),
            sleep_time=_time(idx, "hora_acostarse"),
        )

        training_days: int = int(_value(idx, "dias_entreno_disponibles"))
        rest_days: int = int(_value(idx, "dias_descanso_total", default=7 - training_days))
        activity: ActivityProfile = ActivityProfile(
            training_days_per_week=training_days,
            rest_days_per_week=rest_days,
            current_training_type=_value(idx, "tipo_entreno_previo"),
            training_time=_time(idx, "hora_entreno"),
            neat_level=_NEAT_MAP[_value(idx, "neat_nivel", default="moderado")],
            injuries=_split_csv(_value(idx, "lesiones_molestias")),
        )

        # Alergias e intolerancias se introducen en una sola pregunta separadas por coma.
        alergias_raw: list[str] = _split_csv(_value(idx, "alergias_intolerancias"))
        comfortable: list[str] = _split_csv(_value(idx, "comodidad_cocinar"))
        on_the_go: list[str] = _split_csv(_value(idx, "comodidad_fuera"))
        # Combinamos preferencias domésticas y fuera de casa como "cómodos".
        comfortable_set: list[str] = list(dict.fromkeys(comfortable + on_the_go))

        nutrition: NutritionProfile = NutritionProfile(
            current_calories=_value(idx, "kcals_actuales"),
            current_macros=None,
            meals_per_day=int(_value(idx, "numero_comidas_dia")),
            typical_foods=_value(idx, "alimentos_habituales", default=""),
            disliked_foods=_split_csv(_value(idx, "alimentos_no_gusta")),
            allergies=alergias_raw,
            intolerances=[],
            salt_usage=_SALT_MAP[_value(idx, "cantidad_sal", default="moderada")],
            daily_water_liters=float(_value(idx, "agua_litros_dia", default=0)),
            habitual_drinks=_split_csv(_value(idx, "bebidas_habituales")),
            comfortable_food_groups=comfortable_set,
            uncomfortable_food_groups=[],
            open_to_supplements=_bool(idx, "abierto_suplementos"),
            open_to_fasting=_bool(idx, "ventana_horaria_reducida"),
            open_to_skip_breakfast=_bool(idx, "saltarse_desayuno"),
            open_to_reduced_window=_bool(idx, "ventana_horaria_reducida"),
        )

        goals: Goals = Goals(
            primary_goal=_value(idx, "objetivo_principal"),
            primary_goal_detail=_value(idx, "objetivo_detallado", default=""),
            secondary_goals=_split_csv(_value(idx, "objetivos_secundarios")),
            target_timeframe=_value(idx, "plazo"),
            priority_body_areas=_split_csv(_value(idx, "zonas_prioritarias")),
        )

        # Las fotos llegan en `image_paths`, no en `value`.
        gym_photo_resp: QuestionnaireResponse | None = idx.get("equipamiento_fotos_paths")
        gym_photos: list[str] = list(gym_photo_resp.image_paths or []) if gym_photo_resp else []
        gym: GymEquipment = GymEquipment(
            available_equipment=[],
            equipment_notes=_value(idx, "material_gimnasio"),
            equipment_photo_paths=gym_photos,
        )

        body_photo_paths: list[str] = []
        for qid in (
            "foto_frente",
            "foto_espalda",
            "foto_perfil_izquierdo",
            "foto_perfil_derecho",
        ):
            r: QuestionnaireResponse | None = idx.get(qid)
            if r and r.image_paths:
                body_photo_paths.extend(r.image_paths)

        return cls(
            id=user_id or uuid.uuid4().hex[:12],
            created_at=now,
            updated_at=now,
            personal=personal,
            activity=activity,
            nutrition=nutrition,
            goals=goals,
            gym=gym,
            body_photo_paths=body_photo_paths,
        )
