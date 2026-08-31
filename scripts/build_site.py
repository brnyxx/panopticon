"""Build the deterministic bilingual Panopticon landing page."""

from __future__ import annotations

import argparse
import ctypes
import html
import json
import os
import platform
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = ROOT / "site"
LOCALES = ("en", "ko")
ASSETS = ("site.css", "site.js", "logo.svg")
PLACEHOLDER = re.compile(r"{{([a-z][a-z0-9_]*)}}")
BUILD_KEYS = frozenset({"asset_prefix", "en_current", "ko_current"})


class SiteBuildError(ValueError):
    """The static-site source contract is invalid."""


def load_content(content_dir: Path) -> dict[str, dict[str, str]]:
    """Load locale JSON and reject non-string values or key drift."""
    catalogs: dict[str, dict[str, str]] = {}
    for locale in LOCALES:
        path = content_dir / f"{locale}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise SiteBuildError(f"INVALID_LOCALE:{locale}") from exc
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
        ):
            raise SiteBuildError(f"INVALID_LOCALE_VALUES:{locale}")
        catalogs[locale] = payload

    english_keys = set(catalogs["en"])
    if set(catalogs["ko"]) != english_keys:
        raise SiteBuildError("LOCALE_KEY_MISMATCH")
    return catalogs


def template_keys(template: str) -> frozenset[str]:
    """Return placeholders after rejecting malformed template markers."""
    keys = frozenset(PLACEHOLDER.findall(template))
    remainder = PLACEHOLDER.sub("", template)
    if "{{" in remainder or "}}" in remainder:
        raise SiteBuildError("MALFORMED_PLACEHOLDER")
    return keys


def render(template: str, catalog: Mapping[str, str], locale: str) -> str:
    """Render one route, escaping locale text and using fixed build fragments."""
    placeholders = template_keys(template)
    unknown = placeholders - set(catalog) - BUILD_KEYS
    if unknown:
        raise SiteBuildError(f"UNKNOWN_PLACEHOLDER:{','.join(sorted(unknown))}")

    build_values = {
        "asset_prefix": "" if locale == "en" else "../",
        "en_current": 'aria-current="page"' if locale == "en" else "",
        "ko_current": 'aria-current="page"' if locale == "ko" else "",
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in build_values:
            return build_values[key]
        return html.escape(catalog[key], quote=True)

    rendered = PLACEHOLDER.sub(replace, template)
    if PLACEHOLDER.search(rendered):
        raise SiteBuildError("UNRESOLVED_PLACEHOLDER")
    return rendered.rstrip() + "\n"


def _write_tree(staging: Path, source: Path) -> None:
    template = (source / "template.html").read_text(encoding="utf-8")
    catalogs = load_content(source / "content")
    required = template_keys(template) - BUILD_KEYS
    missing = required - set(catalogs["en"])
    if missing:
        raise SiteBuildError(f"MISSING_LOCALE_KEY:{','.join(sorted(missing))}")

    (staging / "ko").mkdir(parents=True)
    (staging / "assets").mkdir()
    (staging / "index.html").write_text(
        render(template, catalogs["en"], "en"), encoding="utf-8", newline="\n"
    )
    (staging / "ko" / "index.html").write_text(
        render(template, catalogs["ko"], "ko"), encoding="utf-8", newline="\n"
    )
    for name in ASSETS:
        source_asset = source / "assets" / name
        if not source_asset.is_file():
            raise SiteBuildError(f"MISSING_ASSET:{name}")
        shutil.copyfile(source_asset, staging / "assets" / name)


def _exchange_directories(staging: Path, destination: Path) -> None:
    """Atomically exchange two directories on supported production platforms."""
    libc = ctypes.CDLL(None, use_errno=True)
    old = os.fsencode(staging)
    new = os.fsencode(destination)
    system = platform.system()
    if system == "Darwin":
        exchange = libc.renameatx_np
        exchange.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        exchange.restype = ctypes.c_int
        result = exchange(-2, old, -2, new, 0x00000002)
    elif system == "Linux" and hasattr(libc, "renameat2"):
        exchange = libc.renameat2
        exchange.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        exchange.restype = ctypes.c_int
        result = exchange(-100, old, -100, new, 0x00000002)
    else:
        raise SiteBuildError("ATOMIC_REPLACE_UNSUPPORTED")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, "atomic directory exchange failed")


def _validate_paths(source: Path, destination: Path) -> None:
    if destination.is_symlink():
        raise SiteBuildError("OUTPUT_SYMLINK_UNSUPPORTED")
    source_path = source.resolve()
    destination_path = destination.resolve(strict=False)
    if (
        source_path == destination_path
        or source_path in destination_path.parents
        or destination_path in source_path.parents
    ):
        raise SiteBuildError("SOURCE_OUTPUT_OVERLAP")
    if destination_path.exists() and not destination_path.is_dir():
        raise SiteBuildError("OUTPUT_NOT_DIRECTORY")


def build(output: Path, *, source: Path = SITE_ROOT) -> None:
    """Build and validate in a sibling directory before replacing the output."""
    destination = output.absolute()
    _validate_paths(source, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(mkdtemp(prefix=f".{destination.name}.build-", dir=destination.parent))
    try:
        _write_tree(staging, source.resolve())
        if destination.exists():
            _exchange_directories(staging, destination)
        else:
            staging.replace(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
