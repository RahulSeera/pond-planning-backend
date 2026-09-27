"""Shared pytest setup: keep test runs from overwriting the tracked data/analyses_history.json."""

import os

import pytest

# Keep the background Open-Meteo probe thread from changing circuit-breaker state mid-test.
os.environ["BHAGIRATHA_DISABLE_RAINFALL_PROBE"] = "1"


@pytest.fixture(autouse=True)
def _isolated_history_file(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "HISTORY_FILE", str(tmp_path / "analyses_history.json"))
    monkeypatch.setattr(main, "DATA_DIR", str(tmp_path))
    yield
