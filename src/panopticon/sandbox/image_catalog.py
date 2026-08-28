"""Offline, digest-pinned sandbox image catalog."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGES: Mapping[str, tuple[str, str, str]] = {
    "node20": ("ghcr.io/brnyxx/pano-sandbox-node:20", "node", "20"),
    "node22": ("ghcr.io/brnyxx/pano-sandbox-node:22", "node", "22"),
    "python312": ("ghcr.io/brnyxx/pano-sandbox-python:3.12", "python", "3.12"),
    "base": ("ghcr.io/brnyxx/pano-sandbox-base:0.1", "generic", "base"),
}
_KEYS = {value[0]: key for key, value in _IMAGES.items()}


class ImageStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class ImageEntry:
    name: str
    digest: str

    @property
    def reference(self) -> str:
        return f"{self.name}@{self.digest}"


@dataclass(frozen=True, slots=True)
class ImageSelection:
    status: ImageStatus
    entry: ImageEntry | None = None
    reason: str | None = None

    @property
    def reference(self) -> str | None:
        return self.entry.reference if self.entry is not None else None

    @property
    def image(self) -> str | None:
        return self.reference

    @property
    def image_ref(self) -> str | None:
        return self.reference


def parse_image_lock(source: str | Path) -> dict[str, ImageEntry]:
    """Parse a lock file, requiring all four published GHCR identities."""
    text = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) else source
    found: dict[str, ImageEntry] = {}
    seen_keys: set[str] = set()
    version_seen = False
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line or line.count("=") != 1:
            raise ValueError(f"malformed image lock line {line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "version":
            if version_seen or value != "1":
                raise ValueError("unsupported or duplicate lock version")
            version_seen = True
            continue
        if not (key.startswith("source.") or key in _KEYS):
            raise ValueError(f"unknown image lock key: {key}")
        if key in seen_keys:
            raise ValueError(f"duplicate image lock key: {key}")
        seen_keys.add(key)
        if not _DIGEST.fullmatch(value):
            raise ValueError(f"malformed digest for {key}")
        if key in _KEYS:
            found[_KEYS[key]] = ImageEntry(key, value)
    if not version_seen:
        raise ValueError("missing lock version")
    missing = sorted(set(_IMAGES) - set(found))
    if missing:
        raise ValueError(f"missing image identities: {', '.join(missing)}")
    return found


def _default_lock() -> Path:
    return Path(__file__).with_name("images.lock")


class ImageCatalog:
    """Immutable catalog loaded from the repository's lock file."""

    def __init__(self, entries: Mapping[str, ImageEntry] | None = None) -> None:
        self._entries = dict(parse_image_lock(_default_lock()) if entries is None else entries)

    @classmethod
    def from_lock(cls, source: str | Path) -> ImageCatalog:
        return cls(parse_image_lock(source))

    @property
    def entries(self) -> Mapping[str, ImageEntry]:
        return self._entries.copy()

    def select(self, ecosystem: str, version: str | int | None = None) -> ImageSelection:
        eco = ecosystem.casefold().strip()
        ver = None if version is None else str(version).strip().casefold()
        key: str | None = None
        if eco in {"npm", "node"} and ver in {"20", "22"}:
            key = f"node{ver}"
        elif eco in {"pypi", "python"} and ver in {"3.12", "312"}:
            key = "python312"
        elif eco in {"generic", "base"} and ver in {None, "", "base", "0.1"}:
            key = "base"
        if key is None:
            return ImageSelection(ImageStatus.UNSUPPORTED, reason="UNSUPPORTED_TARGET")
        entry = self._entries.get(key)
        if entry is None:
            return ImageSelection(ImageStatus.UNSUPPORTED, reason="MISSING_IDENTITY")
        return ImageSelection(ImageStatus.SUPPORTED, entry=entry)

    resolve = select


DEFAULT_IMAGE_CATALOG = ImageCatalog()

__all__ = [
    "DEFAULT_IMAGE_CATALOG",
    "ImageCatalog",
    "ImageEntry",
    "ImageSelection",
    "ImageStatus",
    "parse_image_lock",
]
