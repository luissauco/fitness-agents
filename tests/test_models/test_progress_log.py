"""Tests del registro de progreso bisemanal."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.models.body_assessment import BodyMeasurements
from src.models.progress_log import (
    NutritionAdherence,
    PhotoComparison,
    ProgressDecision,
    ProgressLog,
    SubjectiveFeedback,
    TrainingProgress,
    WeightLog,
)

# ----------------------------------------------------------- WeightLog


def test_weight_log_gaining_trend() -> None:
    log = WeightLog.from_weights([80.5, 81.0, 81.2], last_average=80.0)
    assert log.trend == "gaining"
    assert log.change_from_last > 0


def test_weight_log_losing_trend() -> None:
    log = WeightLog.from_weights([79.5, 79.2, 79.0], last_average=80.0)
    assert log.trend == "losing"
    assert log.change_from_last < 0


def test_weight_log_stable_trend_small_change() -> None:
    log = WeightLog.from_weights([80.1, 80.0, 80.2], last_average=80.0)
    assert log.trend == "stable"


def test_weight_log_stable_when_no_last_average() -> None:
    log = WeightLog.from_weights([80.0, 80.5])
    assert log.trend == "stable"
    assert log.change_from_last is None


def test_weight_log_average_calculated_correctly() -> None:
    log = WeightLog.from_weights([80.0, 82.0])
    assert log.average == 81.0


def test_weight_log_empty_weights_raises() -> None:
    with pytest.raises(ValueError):
        WeightLog.from_weights([])


# ----------------------------------------------------------- TrainingProgress


def test_training_progress_valid() -> None:
    tp = TrainingProgress(
        exercises_tracked=10,
        exercises_progressed=6,
        exercises_stagnated=3,
        exercises_regressed=1,
        volume_adherence_pct=95.0,
    )
    total = tp.exercises_progressed + tp.exercises_stagnated + tp.exercises_regressed
    assert total <= tp.exercises_tracked


def test_training_progress_sum_exceeds_tracked_raises() -> None:
    with pytest.raises(ValidationError):
        TrainingProgress(
            exercises_tracked=5,
            exercises_progressed=3,
            exercises_stagnated=2,
            exercises_regressed=2,  # 3+2+2=7 > 5
            volume_adherence_pct=80.0,
        )


# ----------------------------------------------------------- SubjectiveFeedback


def test_subjective_feedback_scale_bounds_valid() -> None:
    sf = SubjectiveFeedback(
        energy_level=7,
        sleep_quality=6,
        hunger_level=5,
        motivation=8,
        stress_level=4,
        soreness=3,
        mood=7,
    )
    assert 1 <= sf.energy_level <= 10


def test_subjective_feedback_out_of_bounds_raises() -> None:
    with pytest.raises(ValidationError):
        SubjectiveFeedback(
            energy_level=11,  # > 10
            sleep_quality=6,
            hunger_level=5,
            motivation=8,
            stress_level=4,
            soreness=3,
            mood=7,
        )


# ----------------------------------------------------------- ProgressLog


def _make_progress_log(**overrides: object) -> ProgressLog:
    base: dict = {
        "id": "log-001",
        "user_id": "user-001",
        "mesocycle_id": "meso-001",
        "microcycle_number": 2,
        "date": date(2026, 5, 19),
        "period_start": date(2026, 5, 5),
        "period_end": date(2026, 5, 18),
        "weight": WeightLog.from_weights([79.8, 79.5, 79.6], last_average=80.0),
        "measurements": BodyMeasurements(weight_kg=79.6),
        "training": TrainingProgress(
            exercises_tracked=8,
            exercises_progressed=5,
            exercises_stagnated=2,
            exercises_regressed=1,
            volume_adherence_pct=90.0,
        ),
        "nutrition": NutritionAdherence(
            adherence_pct=88.0,
            cheat_meals_count=1,
            missed_meals_avg=0.3,
            supplement_adherence=True,
            water_intake_liters=2.5,
        ),
        "subjective": SubjectiveFeedback(
            energy_level=7,
            sleep_quality=7,
            hunger_level=6,
            motivation=8,
            stress_level=4,
            soreness=3,
            mood=8,
        ),
        "daily_steps_avg": 9800,
        "decision": ProgressDecision(
            action="continue",
            reasoning="Buena progresión, adherencia alta.",
        ),
        "report_summary": "Segunda semana con tendencia bajista y buen rendimiento.",
        "created_at": datetime(2026, 5, 19, 9, 0),
    }
    base.update(overrides)
    return ProgressLog(**base)


def test_progress_log_valid() -> None:
    log = _make_progress_log()
    assert log.microcycle_number == 2
    assert log.weight.trend == "losing"


def test_progress_log_period_start_after_end_raises() -> None:
    with pytest.raises(ValidationError):
        _make_progress_log(
            period_start=date(2026, 5, 20),
            period_end=date(2026, 5, 5),
        )


def test_photo_comparison_requires_current_photos() -> None:
    with pytest.raises(ValidationError):
        PhotoComparison(current_photos=[], visual_changes="Sin cambios.")


def test_progress_decision_continue() -> None:
    d = ProgressDecision(action="continue", reasoning="Todo bien.")
    assert d.action == "continue"
    assert d.details == {}


def test_progress_decision_with_details() -> None:
    d = ProgressDecision(
        action="adjust_calories",
        reasoning="Peso estancado en 80 kg.",
        details={"calorie_change": -150, "new_target": 1950},
    )
    assert d.details["new_target"] == 1950
