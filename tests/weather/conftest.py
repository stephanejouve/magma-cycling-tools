"""Test fixtures for the weather module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def mf_forecast_chas() -> dict[str, Any]:
    return _load_fixture("mf_forecast_chas.json")


@pytest.fixture
def mf_rain_1h_chas() -> dict[str, Any]:
    return _load_fixture("mf_rain_1h_chas.json")


@pytest.fixture
def mf_vigilance_63() -> dict[str, Any]:
    return _load_fixture("mf_vigilance_63.json")
