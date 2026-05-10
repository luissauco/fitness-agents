"""Repositorios SQLite para los modelos del sistema fitness-agents.

Cada repositorio serializa el modelo Pydantic a JSON en la columna `data` y
mantiene metadatos indexables (user_id, fechas) para consultas rápidas. La
forma final del modelo se reconstruye con `model_validate_json`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Final

from src.db.connection import open_connection
from src.models.body_assessment import BodyAssessment
from src.models.mesocycle import Mesocycle
from src.models.nutrition_plan import NutritionPlan
from src.models.progress_log import ProgressLog
from src.models.user_profile import UserProfile


def _now_iso() -> str:
    """ISO-8601 con segundos."""
    return datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------- UserProfile


class UserProfileRepository:
    """CRUD del `UserProfile`. Una fila por usuario (`id` = `user_id`)."""

    _TABLE: Final[str] = "user_profile"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path | None = db_path

    def get(self, user_id: str) -> UserProfile | None:
        """Devuelve el perfil del usuario o `None` si no existe."""
        with open_connection(self._db_path) as conn:
            row: Any = conn.execute(
                f"SELECT data FROM {self._TABLE} WHERE id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return UserProfile.model_validate_json(row["data"])

    def save(self, profile: UserProfile) -> None:
        """Inserta o actualiza el perfil (upsert por `profile.id`)."""
        payload: str = profile.model_dump_json()
        created_at: str = profile.created_at.isoformat(timespec="seconds")
        updated_at: str = profile.updated_at.isoformat(timespec="seconds")
        with open_connection(self._db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TABLE} (id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (profile.id, payload, created_at, updated_at),
            )


# ------------------------------------------------------- BodyAssessment


class BodyAssessmentRepository:
    """CRUD de `BodyAssessment`. Histórico por usuario indexado por fecha."""

    _TABLE: Final[str] = "body_assessment"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path | None = db_path

    def get_latest(self, user_id: str) -> BodyAssessment | None:
        """Última evaluación registrada del usuario."""
        with open_connection(self._db_path) as conn:
            row: Any = conn.execute(
                f"""
                SELECT data FROM {self._TABLE}
                WHERE user_id = ?
                ORDER BY assessed_on DESC, created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return BodyAssessment.model_validate_json(row["data"])

    def save(self, assessment: BodyAssessment) -> None:
        """Inserta o actualiza la evaluación por `id`."""
        payload: str = assessment.model_dump_json()
        with open_connection(self._db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TABLE} (id, user_id, assessed_on, data, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    assessed_on = excluded.assessed_on,
                    data = excluded.data
                """,
                (
                    assessment.id,
                    assessment.user_id,
                    assessment.date.isoformat(),
                    payload,
                    _now_iso(),
                ),
            )


# ----------------------------------------------------------- Mesocycle


class MesocycleRepository:
    """CRUD de `Mesocycle`. `get_current` devuelve el más reciente del usuario."""

    _TABLE: Final[str] = "mesocycle"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path | None = db_path

    def get_current(self, user_id: str) -> Mesocycle | None:
        """Último mesociclo creado para el usuario (no garantiza que esté activo)."""
        with open_connection(self._db_path) as conn:
            row: Any = conn.execute(
                f"""
                SELECT data FROM {self._TABLE}
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return Mesocycle.model_validate_json(row["data"])

    def save(self, mesocycle: Mesocycle) -> None:
        """Upsert por `mesocycle.id`."""
        payload: str = mesocycle.model_dump_json()
        created_at: str = mesocycle.created_at.isoformat(timespec="seconds")
        with open_connection(self._db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TABLE} (id, user_id, data, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data
                """,
                (mesocycle.id, mesocycle.user_id, payload, created_at),
            )

    def list_history(self, user_id: str) -> list[Mesocycle]:
        """Histórico cronológico (más recientes primero)."""
        with open_connection(self._db_path) as conn:
            rows: list[Any] = conn.execute(
                f"""
                SELECT data FROM {self._TABLE}
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [Mesocycle.model_validate_json(r["data"]) for r in rows]


# -------------------------------------------------------- NutritionPlan


class NutritionPlanRepository:
    """CRUD de `NutritionPlan` con misma semántica que `MesocycleRepository`."""

    _TABLE: Final[str] = "nutrition_plan"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path | None = db_path

    def get_current(self, user_id: str) -> NutritionPlan | None:
        """Último plan creado para el usuario."""
        with open_connection(self._db_path) as conn:
            row: Any = conn.execute(
                f"""
                SELECT data FROM {self._TABLE}
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return NutritionPlan.model_validate_json(row["data"])

    def save(self, plan: NutritionPlan) -> None:
        """Upsert por `plan.id`."""
        payload: str = plan.model_dump_json()
        created_at: str = plan.created_at.isoformat(timespec="seconds")
        with open_connection(self._db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TABLE} (id, user_id, data, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data
                """,
                (plan.id, plan.user_id, payload, created_at),
            )


# --------------------------------------------------------- ProgressLog


class ProgressLogRepository:
    """CRUD de `ProgressLog`. Un log por check-in bisemanal."""

    _TABLE: Final[str] = "progress_log"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path | None = db_path

    def list_for_user(self, user_id: str) -> list[ProgressLog]:
        """Histórico cronológico del usuario (más recientes primero)."""
        with open_connection(self._db_path) as conn:
            rows: list[Any] = conn.execute(
                f"""
                SELECT data FROM {self._TABLE}
                WHERE user_id = ?
                ORDER BY log_date DESC, created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [ProgressLog.model_validate_json(r["data"]) for r in rows]

    def save(self, log: ProgressLog) -> None:
        """Upsert por `log.id`."""
        payload: str = log.model_dump_json()
        with open_connection(self._db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self._TABLE}
                    (id, user_id, mesocycle_id, log_date, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data
                """,
                (
                    log.id,
                    log.user_id,
                    log.mesocycle_id,
                    log.date.isoformat(),
                    payload,
                    log.created_at.isoformat(timespec="seconds"),
                ),
            )
