"""Isolate the exact upstream replay package from Panopticon product imports."""

from __future__ import annotations

import sys
from pathlib import Path

_REPLAY_ROOT = Path(__file__).resolve().parent
_REPLAY_SOURCE = _REPLAY_ROOT / "src"

sys.path.insert(0, str(_REPLAY_ROOT))
sys.path.insert(0, str(_REPLAY_SOURCE))
