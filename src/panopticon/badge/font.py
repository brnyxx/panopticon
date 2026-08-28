"""Fail-closed loader for the bundled Nanum Gothic font."""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from pathlib import Path

from PIL import ImageFont

DEFAULT_FONT = Path(__file__).with_name("assets") / "NanumGothic-Regular.ttf"
BUNDLED_FONT_SHA256: frozenset[str] = frozenset(
    {"76f45ef4a6bcff344c837c95a7dcc26e017e38b5846d5ae0cdcb5b86be2e2d31"}
)


def load_font(
    size: int,
    *,
    path: str | Path | None = None,
    allowed_hashes: Collection[str] | None = None,
) -> ImageFont.FreeTypeFont:
    if size <= 0:
        raise ValueError("font size must be positive")
    font_path = Path(path) if path is not None else DEFAULT_FONT
    try:
        payload = font_path.read_bytes()
    except OSError as exc:
        raise ValueError("bundled font is unavailable") from exc
    digest = hashlib.sha256(payload).hexdigest()
    allowlist = frozenset(allowed_hashes) if allowed_hashes is not None else BUNDLED_FONT_SHA256
    if digest not in allowlist:
        raise ValueError("bundled font failed integrity check")
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError as exc:
        raise ValueError("bundled font is invalid") from exc


__all__ = ["BUNDLED_FONT_SHA256", "DEFAULT_FONT", "load_font"]
