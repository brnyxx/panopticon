"""The installed package advertises its public typing contract."""

from __future__ import annotations

from importlib.resources import files


def test_panopticon_package_ships_pep_561_marker() -> None:
    # Given / When: package resources are resolved through the installed distribution.
    marker = files("panopticon").joinpath("py.typed")

    # Then: type checkers can discover Panopticon's inline annotations.
    assert marker.is_file()
