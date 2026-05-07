"""Tests del catálogo de ejercicios y sus métodos de consulta."""

from __future__ import annotations

from src.models.exercise_db import (
    Equipment,
    ExerciseDatabase,
    ForceProfile,
    MovementPattern,
    MuscleGroup,
)


def test_load_fills_catalogue(exercise_db: ExerciseDatabase) -> None:
    assert len(exercise_db) > 0


def test_filter_by_muscle_group_returns_only_matching(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.filter(muscle_group=MuscleGroup.CHEST)
    assert results
    for ex in results:
        assert MuscleGroup.CHEST in ex.primary_muscles or MuscleGroup.CHEST in ex.secondary_muscles


def test_filter_by_equipment_returns_subset_only(exercise_db: ExerciseDatabase) -> None:
    available = [Equipment.DUMBBELL, Equipment.BENCH]
    results = exercise_db.filter(available_equipment=available)
    available_set = set(available)
    for ex in results:
        assert set(ex.equipment).issubset(available_set)


def test_filter_compound_only(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.filter(is_compound=True)
    assert results
    assert all(e.is_compound for e in results)


def test_filter_isolation_only(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.filter(is_compound=False)
    assert results
    assert all(not e.is_compound for e in results)


def test_filter_by_force_profile(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.filter(force_profile=ForceProfile.STRETCHED)
    assert all(e.force_profile == ForceProfile.STRETCHED for e in results)


def test_search_by_name_returns_matches(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.search("sentadilla")
    assert results
    assert all("sentadilla" in e.name.lower() for e in results)


def test_search_case_insensitive(exercise_db: ExerciseDatabase) -> None:
    lower = exercise_db.search("press")
    upper = exercise_db.search("PRESS")
    assert {e.id for e in lower} == {e.id for e in upper}


def test_search_empty_query_returns_empty(exercise_db: ExerciseDatabase) -> None:
    assert exercise_db.search("") == []


def test_by_id_found(exercise_db: ExerciseDatabase) -> None:
    ex = exercise_db.by_id("press-banca-barra-plano")
    assert ex is not None
    assert ex.id == "press-banca-barra-plano"
    assert MuscleGroup.CHEST in ex.primary_muscles


def test_by_id_not_found(exercise_db: ExerciseDatabase) -> None:
    assert exercise_db.by_id("ejercicio-inexistente") is None


def test_complementary_horizontal_push_returns_pulls(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.complementary("press-banca-barra-plano")
    assert results
    assert all(e.movement_pattern == MovementPattern.HORIZONTAL_PULL for e in results)


def test_complementary_unknown_id_returns_empty(exercise_db: ExerciseDatabase) -> None:
    assert exercise_db.complementary("no-existe") == []


def test_filter_combined_criteria(exercise_db: ExerciseDatabase) -> None:
    results = exercise_db.filter(
        muscle_group=MuscleGroup.BACK,
        movement_pattern=MovementPattern.HORIZONTAL_PULL,
        is_compound=True,
    )
    for ex in results:
        assert ex.is_compound
        assert ex.movement_pattern == MovementPattern.HORIZONTAL_PULL
        assert MuscleGroup.BACK in ex.primary_muscles or MuscleGroup.BACK in ex.secondary_muscles
