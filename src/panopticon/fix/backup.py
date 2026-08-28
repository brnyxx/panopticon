"""Secret-safe backup request composition; persistence is delegated to SecretStore."""

from __future__ import annotations

from pathlib import Path

from panopticon.models.common import PersistedPath
from panopticon.secrets.contracts import BackupMetadata, BackupWriteRequest
from panopticon.util.leak_check import LeakContext

from .model import BackupRequest


def encrypted_backup_request(
    request: BackupRequest, leak_context: LeakContext
) -> BackupWriteRequest:
    """Build the opaque secret-boundary request without writing or exposing plaintext."""
    path = str(request.target)
    if request.target.is_absolute():
        path = "~/" + request.target.name
    metadata = BackupMetadata(
        source=request.source,
        config_path=PersistedPath(path),
        config_digest=request.config_digest,
    )
    return BackupWriteRequest(
        request.target, request.plaintext, request.key_name, metadata, leak_context
    )


def backup_target(config: Path, timestamp: str) -> Path:
    """Return deterministic restrictive backup name; caller performs persistence."""
    return config.with_name(f"{config.name}.pano-bak-{timestamp}")
