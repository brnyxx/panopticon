from __future__ import annotations

from pathlib import Path

import pytest

from panopticon.checks.persistence_boundary import check_file, main

ROOT = Path(__file__).resolve().parents[3]


def _source(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_direct_write_checker_rejects_positive_fixture() -> None:
    # Given: source that persists directly outside the approved gateway.
    malicious = ROOT / "tests" / "fixtures" / "checker" / "direct_write.py"

    # When: the AST checker scans the malicious fixture.
    violations = check_file(malicious)

    # Then: the fixture is rejected with a stable machine classification.
    assert violations
    assert {violation.call for violation in violations} == {"write_text"}


@pytest.mark.parametrize("package", ("fix", "install"))
def test_checker_rejects_arbitrary_fix_and_install_modules(package: str, tmp_path: Path) -> None:
    # Given: a direct writer hidden inside a broadly named future package.
    source = _source(
        tmp_path / "src" / "panopticon" / package / "evil.py",
        "from pathlib import Path\nPath('target').write_text('payload')\n",
    )

    # When: the checker evaluates the module path and syntax.
    violations = check_file(source)

    # Then: package membership alone grants no persistence exemption.
    assert {violation.call for violation in violations} == {"write_text"}


@pytest.mark.parametrize(
    "relative",
    (
        Path("src/panopticon/store/gateway.py"),
        Path("src/panopticon/fix/config_patch.py"),
        Path("src/panopticon/install/config_patch.py"),
    ),
)
def test_checker_allows_only_exact_gateway_and_config_patch_paths(
    relative: Path, tmp_path: Path
) -> None:
    # Given: direct persistence syntax in one explicitly approved path.
    source = _source(tmp_path / relative, "from pathlib import Path\nPath('x').write_bytes(b'x')\n")

    # When / Then: only exact approved modules bypass the checker.
    assert check_file(source) == ()


def test_checker_allows_network_and_stdio_writer_calls(tmp_path: Path) -> None:
    # Given: write-shaped streaming APIs that do not persist files.
    source = _source(
        tmp_path / "relay.py",
        "def relay(writer, stdio_stream, socket_stream, data):\n"
        "    writer.write(data)\n"
        "    stdio_stream.write(data)\n"
        "    socket_stream.write(data)\n",
    )

    # When / Then: generic streaming writes are outside the persistence policy.
    assert check_file(source) == ()


def test_checker_catches_file_handle_and_persistence_forms(tmp_path: Path) -> None:
    # Given: file-provenance writes plus open, path, temp, and replacement forms.
    source = _source(
        tmp_path / "persistence.py",
        "import os\nimport tempfile\nfrom pathlib import Path\n"
        "def persist(path, lines):\n"
        "    with path.open('w') as file_handle:\n"
        "        file_handle.write('x')\n"
        "        file_handle.writelines(lines)\n"
        "    Path('bytes').write_bytes(b'x')\n"
        "    tempfile.NamedTemporaryFile()\n"
        "    os.replace('source', 'target')\n",
    )

    # When: the checker traces file-handle provenance and persistence calls.
    calls = {violation.call for violation in check_file(source)}

    # Then: all machine persistence shapes are rejected.
    assert calls == {
        "NamedTemporaryFile",
        "file-write",
        "file-writelines",
        "os.replace",
        "path-open-write-mode",
        "write_bytes",
    }


def test_checker_rejects_import_aliases_for_claimed_persistence_apis(tmp_path: Path) -> None:
    # Given: direct persistence hidden behind import aliases, not a general data-flow program.
    source = _source(
        tmp_path / "aliased_persistence.py",
        "from builtins import open as file_open\n"
        "from os import replace as swap\n"
        "import os as operating\n"
        "from pathlib import Path as FilePath\n"
        "import tempfile as scratch\n"
        "\n"
        "def persist():\n"
        "    FilePath('target').write_text('payload')\n"
        "    scratch.NamedTemporaryFile()\n"
        "    with file_open('target', 'w') as file_handle:\n"
        "        file_handle.write('payload')\n"
        "    swap('source', 'target')\n"
        "    operating.replace('source', 'target')\n",
    )

    # When: the checker evaluates the aliased persistence calls.
    calls = sorted(violation.call for violation in check_file(source))

    # Then: every claimed API alias is rejected, including both os.replace aliases.
    assert calls == [
        "NamedTemporaryFile",
        "file-write",
        "open-write-mode",
        "os.replace",
        "os.replace",
        "write_text",
    ]


def test_direct_write_checker_accepts_repository_product_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: the complete product source tree.
    # When: the typed checker entry point scans every Python source module.
    result = main((str(ROOT / "src"),))

    # Then: only approved gateway persistence exists.
    assert result == 0
    assert capsys.readouterr().out == ""
