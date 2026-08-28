from __future__ import annotations

from pathlib import Path

from ._support import (
    JSONC_SOURCE,
    AtomicOperation,
    ConcurrentReplacementInjector,
    DocumentSpec,
    PatchSpec,
    WriteSpec,
    apply_patches,
    assert_no_temp_residue,
    machine_value,
    make_patch,
    parse_document,
    require_jsonc_api,
    write_source,
)


def test_concurrent_target_bytes_are_preserved_at_atomic_replace_boundary(
    tmp_path: Path,
) -> None:
    # Given: a parsed source and a same-inode concurrent replacement at the final seam.
    target = tmp_path / "config.jsonc"
    write_source(target)
    api = require_jsonc_api()
    document = parse_document(api, DocumentSpec(JSONC_SOURCE, target))
    patch = make_patch(api, PatchSpec("REPLACE", "/mcpServers/fixture/command", "node"))
    concurrent_bytes = b'{"concurrent":true}\n'

    # When: the atomic REPLACE injector changes target bytes after temp fsync.
    result = apply_patches(
        api,
        WriteSpec(target, document, (patch,)),
        ConcurrentReplacementInjector(AtomicOperation.REPLACE, target, concurrent_bytes),
    )

    # Then: the identity-preserving concurrent bytes win and the temp is removed.
    assert machine_value(result.status) == "CONFLICT"
    assert machine_value(result.reason_code) == "SOURCE_STALE"
    assert result.bytes_written == 0
    assert target.read_bytes() == concurrent_bytes
    assert_no_temp_residue(tmp_path, target)
