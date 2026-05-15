"""Tests del WorkflowRunner: mock del workflow LangGraph."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.state import FitnessState
from src.models.checkin_input import CheckinInput
from src.telegram_bot.services.workflow_runner import WorkflowInput, WorkflowOutput, WorkflowRunner

# ---------------------------------------------------------------- Helpers


def _make_state(**overrides) -> FitnessState:
    """Estado mínimo para tests."""
    base: FitnessState = FitnessState(
        user_id="tg_test123",
        current_phase="onboarding",
        generated_files=[],
        errors=[],
        warnings=[],
    )
    base.update(overrides)  # type: ignore[attr-defined]
    return base


def _make_runner(
    final_state: FitnessState, prev_state_values: dict | None = None
) -> WorkflowRunner:
    """Runner con workflow mockeado que devuelve `final_state`."""
    workflow = MagicMock()
    workflow.ainvoke = AsyncMock(return_value=final_state)

    snapshot = MagicMock()
    snapshot.values = prev_state_values or {}
    workflow.aget_state = AsyncMock(return_value=snapshot)

    repos = MagicMock()
    return WorkflowRunner(workflow=workflow, repos=repos)


# -------------------------------------------------------- Tests invoke


@pytest.mark.asyncio
async def test_onboarding_nuevo_usuario_retorna_needs_user_input():
    """Usuario nuevo en onboarding: output con needs_user_input=True."""
    state = _make_state(current_phase="onboarding")
    runner = _make_runner(final_state=state, prev_state_values=None)

    wf_input = WorkflowInput(user_id="tg_test123", phase_hint="onboarding")
    output: WorkflowOutput = await runner.invoke(wf_input)

    assert output.current_phase == "onboarding"
    assert output.needs_user_input is True
    assert output.is_complete is False


@pytest.mark.asyncio
async def test_onboarding_completo_retorna_is_complete():
    """Cuando el workflow termina en fase 'active', is_complete=True."""
    state = _make_state(
        current_phase="active",
        generated_files=["output/Mesociclo.xlsx", "output/Dieta.pdf"],
    )
    runner = _make_runner(final_state=state)

    output = await runner.invoke(WorkflowInput(user_id="tg_test123"))

    assert output.is_complete is True
    assert len(output.generated_files) == 2


@pytest.mark.asyncio
async def test_solo_archivos_nuevos_en_output():
    """generated_files solo incluye archivos que no estaban en el estado previo."""
    prev = {"generated_files": ["output/Mesociclo.xlsx"]}
    state = _make_state(
        current_phase="active",
        generated_files=["output/Mesociclo.xlsx", "output/Progreso.pdf"],
    )
    runner = _make_runner(final_state=state, prev_state_values=prev)

    output = await runner.invoke(WorkflowInput(user_id="tg_test123"))

    assert output.generated_files == [Path("output/Progreso.pdf")]


@pytest.mark.asyncio
async def test_checkin_input_se_envía_al_grafo():
    """Con checkin_data en el input, el grafo recibe pending_checkin_data y phase=checkin."""
    state = _make_state(current_phase="active")
    runner = _make_runner(final_state=state)

    checkin = MagicMock(spec=CheckinInput)
    wf_input = WorkflowInput(user_id="tg_test123", checkin_data=checkin)
    await runner.invoke(wf_input)

    call_args = runner._workflow.ainvoke.call_args[0][0]
    assert call_args["pending_checkin_data"] is checkin
    assert call_args["current_phase"] == "checkin"


@pytest.mark.asyncio
async def test_imagen_paths_se_envían_al_grafo():
    """Con image_paths, el grafo recibe pending_user_images con los paths como strings."""
    state = _make_state()
    runner = _make_runner(final_state=state)

    paths = [Path("data/photos/user1/body/foto.jpg")]
    await runner.invoke(WorkflowInput(user_id="tg_test123", image_paths=paths))

    call_args = runner._workflow.ainvoke.call_args[0][0]
    assert call_args["pending_user_images"] == ["data/photos/user1/body/foto.jpg"]


@pytest.mark.asyncio
async def test_dos_user_ids_distintos_usan_thread_ids_distintos():
    """Usuarios distintos → thread_ids distintos en la config del grafo."""
    state = _make_state()
    runner = _make_runner(final_state=state)

    await runner.invoke(WorkflowInput(user_id="user_a"))
    config_a = runner._workflow.ainvoke.call_args[1]["config"]

    await runner.invoke(WorkflowInput(user_id="user_b"))
    config_b = runner._workflow.ainvoke.call_args[1]["config"]

    assert config_a["configurable"]["thread_id"] == "user_a"
    assert config_b["configurable"]["thread_id"] == "user_b"
    assert config_a != config_b


@pytest.mark.asyncio
async def test_errors_y_warnings_se_propagan():
    """Errores y warnings del estado se exponen en el output."""
    state = _make_state(errors=["fallo x"], warnings=["aviso y"])
    runner = _make_runner(final_state=state)

    output = await runner.invoke(WorkflowInput(user_id="tg_test123"))

    assert output.errors == ["fallo x"]
    assert output.warnings == ["aviso y"]


@pytest.mark.asyncio
async def test_next_checkin_date_se_propaga():
    """next_checkin_date del estado se expone en el output."""
    hoy = date(2026, 5, 29)
    state = _make_state(current_phase="active", next_checkin_date=hoy)
    runner = _make_runner(final_state=state)

    output = await runner.invoke(WorkflowInput(user_id="tg_test123"))

    assert output.next_checkin_date == hoy


@pytest.mark.asyncio
async def test_persist_artifacts_se_llama_tras_invoke():
    """persist_artifacts se invoca después de cada ainvoke."""
    state = _make_state()
    runner = _make_runner(final_state=state)

    with patch("src.telegram_bot.services.workflow_runner.persist_artifacts") as mock_persist:
        await runner.invoke(WorkflowInput(user_id="tg_test123"))
        mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_usuario_existente_no_incluye_initial_state():
    """Con estado previo, el input al grafo solo contiene el delta (no initial_state)."""
    prev = {"current_phase": "onboarding", "user_id": "tg_test123"}
    state = _make_state()
    runner = _make_runner(final_state=state, prev_state_values=prev)

    await runner.invoke(WorkflowInput(user_id="tg_test123", user_message="hola"))

    call_args = runner._workflow.ainvoke.call_args[0][0]
    # No debe incluir session_id (campo de initial_state) si el usuario ya existe
    assert "session_id" not in call_args
