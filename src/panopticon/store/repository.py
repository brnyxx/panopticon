"""Leak-checked observation and baseline repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from panopticon.baseline.migrate import migrate_baseline_json
from panopticon.models.artifacts import Baseline, WrapRecord
from panopticon.models.ids import BaselineId, InstallationId
from panopticon.models.observation import Observation
from panopticon.store.contracts import (
    AtomicOperation,
    FailureCode,
    FaultInjector,
    ModelArtifact,
    PersistFailure,
    PersistRequest,
    PersistResult,
    PersistSuccess,
    SinkKind,
)
from panopticon.store.gateway import persist
from panopticon.util.leak_check import LeakContext


class LoadStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_FOUND = "NOT_FOUND"
    INVALID = "INVALID"
    PERMISSION = "PERMISSION"


class RemoveStatus(StrEnum):
    REMOVED = "REMOVED"
    NOT_FOUND = "NOT_FOUND"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BaselineLoad:
    status: LoadStatus
    baseline: Baseline | None = None
    reason_code: str = "OK"


@dataclass(frozen=True, slots=True)
class ObservationLoad:
    status: LoadStatus
    observation: Observation | None = None
    reason_code: str = "OK"


class ArtifactRepository:
    def __init__(
        self,
        root: Path | None = None,
        context: LeakContext | None = None,
    ) -> None:
        self.root = root or Path.home() / ".panopticon"
        self.context = context or LeakContext(home_paths=(str(Path.home()),))

    @staticmethod
    def _prepare(target: Path, kind: SinkKind) -> PersistFailure | None:
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except PermissionError:
            return PersistFailure(
                target,
                kind,
                FailureCode.PERMISSION_DENIED,
                AtomicOperation.OPEN_PARENT,
                False,
            )
        except OSError:
            return PersistFailure(
                target,
                kind,
                FailureCode.FILESYSTEM_ERROR,
                AtomicOperation.OPEN_PARENT,
                False,
            )
        return None

    def persist_request(
        self,
        request: PersistRequest,
        context: LeakContext | None = None,
        injector: FaultInjector | None = None,
    ) -> PersistResult:
        failure = self._prepare(request.target, request.artifact.kind)
        if failure is not None:
            return failure
        return persist(request, context or self.context, injector)

    def persist_observation(self, observation: Observation) -> PersistResult:
        target = (
            self.root
            / "observations"
            / str(observation.installation_id)
            / f"{observation.observation_id}.json"
        )
        failure = self._prepare(target, SinkKind.OBSERVATION)
        if failure is not None:
            return failure
        return persist(
            PersistRequest(target, ModelArtifact(SinkKind.OBSERVATION, observation)),
            self.context,
        )

    def persist_baseline(self, baseline: Baseline) -> PersistResult:
        target = self.root / "baselines" / f"{baseline.baseline_id}.json"
        failure = self._prepare(target, SinkKind.BASELINE)
        if failure is not None:
            return failure
        return persist(
            PersistRequest(target, ModelArtifact(SinkKind.BASELINE, baseline)),
            self.context,
        )

    def persist_wrap_record(self, record: WrapRecord) -> PersistResult:
        day = record.ts.date().isoformat()
        span_file = str(record.span.span_id).replace(":", "_")
        target = self.root / "wrap" / str(record.installation_id) / day / f"{span_file}.json"
        failure = self._prepare(target, SinkKind.WRAP_RECORD)
        if failure is not None:
            return failure
        result = persist(
            PersistRequest(target, ModelArtifact(SinkKind.WRAP_RECORD, record)),
            self.context,
        )
        if isinstance(result, PersistSuccess):
            self._prune_wrap_records(record)
        return result

    def _prune_wrap_records(self, current: WrapRecord, keep_days: int = 30) -> None:
        cutoff = current.ts.date() - timedelta(days=keep_days - 1)
        installation = self.root / "wrap" / str(current.installation_id)
        try:
            if installation.is_symlink():
                return
            days = tuple(installation.iterdir())
        except OSError:
            return
        for day_path in days:
            try:
                day = date.fromisoformat(day_path.name)
            except ValueError:
                continue
            if day >= cutoff or day_path.is_symlink() or not day_path.is_dir():
                continue
            try:
                entries = tuple(day_path.iterdir())
                for entry in entries:
                    if entry.suffix == ".json" and not entry.is_symlink() and entry.is_file():
                        entry.unlink()
                day_path.rmdir()
            except OSError:
                continue

    def load_baseline(self, baseline_id: BaselineId | str) -> BaselineLoad:
        path = self.root / "baselines" / f"{baseline_id}.json"
        if path.is_symlink():
            return BaselineLoad(LoadStatus.INVALID, reason_code="SYMLINK_REJECTED")
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return BaselineLoad(LoadStatus.NOT_FOUND, reason_code="BASELINE_NOT_FOUND")
        except PermissionError:
            return BaselineLoad(LoadStatus.PERMISSION, reason_code="BASELINE_PERMISSION")
        except OSError:
            return BaselineLoad(LoadStatus.INVALID, reason_code="BASELINE_READ_FAILED")
        try:
            return BaselineLoad(LoadStatus.AVAILABLE, migrate_baseline_json(payload))
        except (ValidationError, ValueError):
            return BaselineLoad(LoadStatus.INVALID, reason_code="BASELINE_INVALID")

    def list_baselines(self) -> tuple[BaselineLoad, ...]:
        directory = self.root / "baselines"
        try:
            paths = tuple(sorted(directory.glob("bl_*.json"), key=lambda item: item.name))
        except OSError:
            return (BaselineLoad(LoadStatus.INVALID, reason_code="BASELINE_LIST_FAILED"),)
        return tuple(self.load_baseline(path.stem) for path in paths)

    def load_observation(self, path: Path) -> ObservationLoad:
        if path.is_symlink():
            return ObservationLoad(LoadStatus.INVALID, reason_code="SYMLINK_REJECTED")
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ObservationLoad(LoadStatus.NOT_FOUND, reason_code="OBSERVATION_NOT_FOUND")
        except PermissionError:
            return ObservationLoad(LoadStatus.PERMISSION, reason_code="OBSERVATION_PERMISSION")
        except OSError:
            return ObservationLoad(LoadStatus.INVALID, reason_code="OBSERVATION_READ_FAILED")
        try:
            return ObservationLoad(
                LoadStatus.AVAILABLE,
                Observation.model_validate_json(payload),
            )
        except (ValidationError, ValueError):
            return ObservationLoad(LoadStatus.INVALID, reason_code="OBSERVATION_INVALID")

    def latest_observations(self) -> tuple[Observation, ...]:
        directory = self.root / "observations"
        try:
            paths = tuple(sorted(directory.glob("inst_*/obs_*.json")))
        except OSError:
            return ()
        latest: dict[InstallationId, Observation] = {}
        for path in paths:
            loaded = self.load_observation(path)
            if loaded.observation is None:
                continue
            observation = loaded.observation
            previous = latest.get(observation.installation_id)
            if previous is None or (
                observation.observed_at,
                str(observation.observation_id),
            ) > (previous.observed_at, str(previous.observation_id)):
                latest[observation.installation_id] = observation
        return tuple(latest[key] for key in sorted(latest, key=str))

    def remove_baseline(self, baseline_id: BaselineId | str) -> RemoveStatus:
        path = self.root / "baselines" / f"{baseline_id}.json"
        if path.is_symlink():
            return RemoveStatus.REJECTED
        try:
            path.unlink()
        except FileNotFoundError:
            return RemoveStatus.NOT_FOUND
        except PermissionError:
            return RemoveStatus.REJECTED
        except OSError:
            return RemoveStatus.FAILED
        return RemoveStatus.REMOVED


__all__ = [
    "ArtifactRepository",
    "BaselineLoad",
    "LoadStatus",
    "ObservationLoad",
    "RemoveStatus",
]
