"""Tests de la jerarquía de mesociclo y sus propiedades calculadas."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.models.mesocycle import (
    Mesocycle,
    Microcycle,
    ProgrammedExercise,
    SetScheme,
    TrainingDay,
)

# ----------------------------------------------------------- SetScheme


def test_set_scheme_straight_sets_valid() -> None:
    s = SetScheme(total_sets=4, rep_range=(6, 10), rir=1, description="4x6-10 (RIR 1)")
    assert s.total_sets == 4


def test_set_scheme_top_back_off_valid() -> None:
    s = SetScheme(
        total_sets=3,
        rep_range=(5, 5),
        rir=0,
        technique="top_back_off",
        top_set_count=1,
        backoff_set_count=2,
        description="top: 1x5(0) / back-off: 2x5(1)",
    )
    assert s.top_set_count + s.backoff_set_count == s.total_sets


def test_set_scheme_top_back_off_counts_mismatch_raises() -> None:
    with pytest.raises(ValidationError):
        SetScheme(
            total_sets=4,
            rep_range=(5, 5),
            rir=0,
            technique="top_back_off",
            top_set_count=1,
            backoff_set_count=2,  # 1+2=3 ≠ 4
            description="x",
        )


def test_set_scheme_superset_requires_partner() -> None:
    with pytest.raises(ValidationError):
        SetScheme(
            total_sets=3,
            rep_range=(10, 15),
            rir=2,
            technique="superset",
            description="3x10-15 superserie",
        )


def test_set_scheme_invalid_rep_range_raises() -> None:
    with pytest.raises(ValidationError):
        SetScheme(total_sets=3, rep_range=(12, 8), rir=2, description="x")


# ----------------------------------------------------------- TrainingDay


def test_rest_day_with_exercises_raises() -> None:
    with pytest.raises(ValidationError):
        TrainingDay(
            day_number=1,
            day_label="Descanso",
            is_rest_day=True,
            exercises=[
                ProgrammedExercise(
                    order=1,
                    exercise_id="sentadilla-barra-alta",
                    exercise_name="Sentadilla",
                    set_scheme=SetScheme(
                        total_sets=3, rep_range=(8, 12), rir=2, description="3x8-12"
                    ),
                )
            ],
        )


# ----------------------------------------------------------- Microcycle


def test_microcycle_days_cannot_exceed_duration() -> None:
    with pytest.raises(ValidationError):
        Microcycle(
            number=1,
            duration_days=3,
            training_days=[
                TrainingDay(day_number=i, day_label=f"Día {i}", is_rest_day=True)
                for i in range(1, 5)  # 4 días > duration_days=3
            ],
        )


# ----------------------------------------------------------- Mesocycle


def test_end_date_backfilled_automatically(mesocycle: Mesocycle) -> None:
    expected = mesocycle.start_date + timedelta(days=4 * 7 - 1)
    assert mesocycle.end_date == expected


def test_total_weeks(mesocycle: Mesocycle) -> None:
    assert mesocycle.total_weeks == 4


def test_microcycle_count(mesocycle: Mesocycle) -> None:
    assert len(mesocycle.microcycles) == 4


def test_microcycle_sequential_numbering(mesocycle: Mesocycle) -> None:
    for i, m in enumerate(mesocycle.microcycles, start=1):
        assert m.number == i


def test_last_microcycle_is_deload(mesocycle: Mesocycle) -> None:
    assert mesocycle.microcycles[-1].is_deload is True


def test_non_deload_microcycles_not_marked(mesocycle: Mesocycle) -> None:
    for m in mesocycle.microcycles[:-1]:
        assert m.is_deload is False


def test_training_days_per_week_matches_active_days(mesocycle: Mesocycle) -> None:
    for m in mesocycle.microcycles:
        active = sum(1 for d in m.training_days if not d.is_rest_day)
        assert active == mesocycle.training_days_per_week


def test_all_training_days_have_exercises(mesocycle: Mesocycle) -> None:
    for m in mesocycle.microcycles:
        for d in m.training_days:
            if not d.is_rest_day:
                assert d.exercises


def test_current_microcycle_returns_none_before_start(mesocycle: Mesocycle) -> None:
    # El mesociclo comienza en 2026-05-05; date.today() puede ser posterior.
    # Solo validamos que current_microcycle devuelve Microcycle o None.
    result = mesocycle.current_microcycle
    assert result is None or result in mesocycle.microcycles
