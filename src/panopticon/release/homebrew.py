"""Render the Homebrew formula from one verified release manifest."""

from __future__ import annotations

from collections.abc import Mapping

from .manifest import validate_version

_TARGETS = {
    "macos": ("darwin-arm64", "darwin-x86_64"),
    "linux": ("linux-arm64", "linux-x86_64"),
}


def _artifact(hashes: Mapping[str, str], target: str, version: str) -> tuple[str, str]:
    archive = f"panopticon-{version}-{target}.tar.gz"
    digest = hashes.get(archive, "")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"INVALID_HOMEBREW_DIGEST:{archive}")
    return archive, digest


def _platform_block(hashes: Mapping[str, str], base_url: str, os_name: str, version: str) -> str:
    arm_archive, arm_digest = _artifact(hashes, _TARGETS[os_name][0], version)
    intel_archive, intel_digest = _artifact(hashes, _TARGETS[os_name][1], version)
    return f'''  on_{os_name} do
    if Hardware::CPU.arm?
      url "{base_url}{arm_archive}"
      sha256 "{arm_digest}"
    else
      url "{base_url}{intel_archive}"
      sha256 "{intel_digest}"
    end
  end'''


def render_formula(hashes: Mapping[str, str], base_url: str, version: str) -> str:
    version = validate_version(version)
    expected_url = f"https://github.com/brnyxx/panopticon/releases/download/v{version}/"
    if base_url != expected_url:
        raise ValueError("INVALID_HOMEBREW_RELEASE_URL")
    platforms = "\n".join(
        _platform_block(hashes, base_url, os_name, version) for os_name in ("macos", "linux")
    )
    return f"""class Panopticon < Formula
  desc "Local-first MCP behavior observatory"
  homepage "https://github.com/brnyxx/panopticon"
  license "MIT"

{platforms}

  def install
    bin.install "pano"
  end

  test do
    assert_match "pano {version} (schema 1.0)", shell_output("#{{bin}}/pano version")
  end
end
"""
