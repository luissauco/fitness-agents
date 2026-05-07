"""Catálogo de ejercicios y su metadata biomecánica.

Define los enums (`MuscleGroup`, `MovementPattern`, `Equipment`, `ForceProfile`),
el modelo `Exercise` y la clase `ExerciseDatabase` que opera sobre el catálogo
cargado desde `data/exercises.json`.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator

from src.config.settings import PROJECT_ROOT

# --------------------------------------------------------------------- Enums


class MuscleGroup(str, Enum):
    """Grupos musculares principales."""

    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ABS = "abs"
    FOREARMS = "forearms"
    ADDUCTORS = "adductors"
    TRAPS = "traps"
    REAR_DELTS = "rear_delts"
    LATERAL_DELTS = "lateral_delts"


class MovementPattern(str, Enum):
    """Patrones de movimiento biomecánicos."""

    HORIZONTAL_PUSH = "horizontal_push"
    VERTICAL_PUSH = "vertical_push"
    HORIZONTAL_PULL = "horizontal_pull"
    VERTICAL_PULL = "vertical_pull"
    KNEE_DOMINANT = "knee_dominant"
    HIP_DOMINANT = "hip_dominant"
    ISOLATION_ARMS = "isolation_arms"
    ISOLATION_SHOULDERS = "isolation_shoulders"
    CORE = "core"
    CALVES = "calves"


class Equipment(str, Enum):
    """Equipamiento necesario para ejecutar el ejercicio."""

    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    CABLE = "cable"
    MACHINE = "machine"
    SMITH_MACHINE = "smith_machine"
    BODYWEIGHT = "bodyweight"
    BANDS = "bands"
    KETTLEBELL = "kettlebell"
    EZ_BAR = "ez_bar"
    PULLUP_BAR = "pullup_bar"
    BENCH = "bench"


class ForceProfile(str, Enum):
    """Perfil de resistencia (curva de fuerza) del ejercicio.

    `STRETCHED` y `SHORTENED` reflejan los conceptos de tensión mecánica
    en posición estirada vs contraída usados por Fran Pérez Jurado.
    """

    STRETCHED = "stretched"
    SHORTENED = "shortened"
    MID_RANGE = "mid_range"
    CONSTANT = "constant"


# --------------------------------------------------------------------- Modelos


class Exercise(BaseModel):
    """Un ejercicio del catálogo con su metadata biomecánica."""

    id: str = Field(..., description="Slug único del ejercicio (kebab-case).")
    name: str = Field(..., description="Nombre en español.")
    name_en: str | None = Field(default=None, description="Nombre en inglés.")
    primary_muscles: list[MuscleGroup] = Field(..., description="Músculos principales reclutados.")
    secondary_muscles: list[MuscleGroup] = Field(
        default_factory=list, description="Músculos secundarios reclutados."
    )
    movement_pattern: MovementPattern
    equipment: list[Equipment] = Field(
        ..., description="Equipamiento necesario (puede combinarse, ej: barbell+bench)."
    )
    force_profile: ForceProfile
    is_compound: bool = Field(..., description="True si recluta múltiples articulaciones.")
    is_unilateral: bool = False
    default_rep_range: tuple[int, int] = Field(
        ..., description="Rango de repeticiones recomendado (min, max)."
    )
    default_rest_seconds: int = Field(..., description="Descanso recomendado entre series.")
    technique_notes: str | None = Field(
        default=None,
        description="Indicaciones técnicas (ángulo de banco, agarre, ROM, etc.).",
    )
    difficulty: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    video_reference: str | None = None

    @field_validator("default_rep_range")
    @classmethod
    def _validate_rep_range(cls, v: tuple[int, int]) -> tuple[int, int]:
        """Garantiza min ≤ max y ambos > 0."""
        lo, hi = v
        if lo <= 0 or hi <= 0 or lo > hi:
            raise ValueError(f"default_rep_range inválido: {v}")
        return v

    @field_validator("primary_muscles", "equipment")
    @classmethod
    def _non_empty(cls, v: list[Any]) -> list[Any]:
        """primary_muscles y equipment no pueden estar vacíos."""
        if not v:
            raise ValueError("Lista no puede estar vacía.")
        return v


# Pares antagonistas a nivel de patrón de movimiento.
_ANTAGONIST_PATTERNS: dict[MovementPattern, MovementPattern] = {
    MovementPattern.HORIZONTAL_PUSH: MovementPattern.HORIZONTAL_PULL,
    MovementPattern.HORIZONTAL_PULL: MovementPattern.HORIZONTAL_PUSH,
    MovementPattern.VERTICAL_PUSH: MovementPattern.VERTICAL_PULL,
    MovementPattern.VERTICAL_PULL: MovementPattern.VERTICAL_PUSH,
    MovementPattern.KNEE_DOMINANT: MovementPattern.HIP_DOMINANT,
    MovementPattern.HIP_DOMINANT: MovementPattern.KNEE_DOMINANT,
}

# Pares antagonistas a nivel de músculo (para patrones de aislamiento).
_ANTAGONIST_MUSCLES: dict[MuscleGroup, MuscleGroup] = {
    MuscleGroup.BICEPS: MuscleGroup.TRICEPS,
    MuscleGroup.TRICEPS: MuscleGroup.BICEPS,
    MuscleGroup.QUADS: MuscleGroup.HAMSTRINGS,
    MuscleGroup.HAMSTRINGS: MuscleGroup.QUADS,
    MuscleGroup.CHEST: MuscleGroup.BACK,
    MuscleGroup.BACK: MuscleGroup.CHEST,
}


class ExerciseDatabase(BaseModel):
    """Catálogo de ejercicios cargable desde JSON con métodos de consulta."""

    exercises: list[Exercise] = Field(default_factory=list)

    # ----------------------------------------------------------- Carga / persistencia

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Carga el catálogo desde JSON (por defecto `data/exercises.json`)."""
        path = path or PROJECT_ROOT / "data" / "exercises.json"
        with path.open(encoding="utf-8") as f:
            data: list[dict[str, Any]] = json.load(f)
        return cls(exercises=[Exercise.model_validate(item) for item in data])

    def save(self, path: Path) -> None:
        """Persiste el catálogo a JSON con indentación legible."""
        payload: list[dict[str, Any]] = [e.model_dump(mode="json") for e in self.exercises]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # --------------------------------------------------------------- Consultas

    def by_id(self, exercise_id: str) -> Exercise | None:
        """Devuelve el ejercicio con ese id, o None si no existe."""
        for ex in self.exercises:
            if ex.id == exercise_id:
                return ex
        return None

    def filter(
        self,
        *,
        muscle_group: MuscleGroup | None = None,
        movement_pattern: MovementPattern | None = None,
        available_equipment: list[Equipment] | None = None,
        is_compound: bool | None = None,
        force_profile: ForceProfile | None = None,
    ) -> list[Exercise]:
        """Filtra el catálogo por uno o varios criterios.

        Si `available_equipment` se pasa, solo retorna ejercicios cuyo equipamiento
        completo está disponible (subconjunto de la lista dada).
        """
        result: list[Exercise] = list(self.exercises)
        if muscle_group is not None:
            result = [
                e
                for e in result
                if muscle_group in e.primary_muscles or muscle_group in e.secondary_muscles
            ]
        if movement_pattern is not None:
            result = [e for e in result if e.movement_pattern == movement_pattern]
        if available_equipment is not None:
            available_set: set[Equipment] = set(available_equipment)
            result = [e for e in result if set(e.equipment).issubset(available_set)]
        if is_compound is not None:
            result = [e for e in result if e.is_compound == is_compound]
        if force_profile is not None:
            result = [e for e in result if e.force_profile == force_profile]
        return result

    def search(self, query: str) -> list[Exercise]:
        """Búsqueda por nombre (es/en). Case-insensitive, substring match."""
        q: str = query.lower().strip()
        if not q:
            return []
        return [
            e
            for e in self.exercises
            if q in e.name.lower() or (e.name_en and q in e.name_en.lower())
        ]

    def complementary(self, exercise_id: str) -> list[Exercise]:
        """Ejercicios antagonistas: mismo eje pero patrón/músculo opuesto.

        Útil para diseñar superseries antagonistas o equilibrar volumen.
        """
        ex: Exercise | None = self.by_id(exercise_id)
        if ex is None:
            return []

        # 1) Antagonista por patrón de movimiento (compuestos).
        antag_pattern: MovementPattern | None = _ANTAGONIST_PATTERNS.get(ex.movement_pattern)
        if antag_pattern is not None:
            return [e for e in self.exercises if e.movement_pattern == antag_pattern]

        # 2) Antagonista por músculo principal (aislamientos).
        if ex.primary_muscles:
            antag_muscle: MuscleGroup | None = _ANTAGONIST_MUSCLES.get(ex.primary_muscles[0])
            if antag_muscle is not None:
                return [e for e in self.exercises if antag_muscle in e.primary_muscles]

        return []

    def __len__(self) -> int:
        """Número de ejercicios en el catálogo."""
        return len(self.exercises)
