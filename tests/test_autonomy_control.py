from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def override_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "autonomy_override.json"
    monkeypatch.setenv("AUTONOMY_OVERRIDE_PATH", str(path))
    yield path


def test_set_and_clear_pause_state(override_path: Path):
    from services.autonomy_control import set_live_submit_paused, read_live_submit_pause_state

    state = set_live_submit_paused(True, reason="maintenance", updated_by="ops")
    assert state["paused"] is True
    assert override_path.exists()

    read_state = read_live_submit_pause_state()
    assert read_state["paused"] is True
    assert "maintenance" in read_state["reason"]

    cleared = set_live_submit_paused(False)
    assert cleared["paused"] is False
    assert not override_path.exists()
