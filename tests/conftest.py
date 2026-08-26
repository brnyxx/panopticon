from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def load_json():
    def _load(rel: str):
        return json.loads((FIXTURES / rel).read_text())

    return _load
