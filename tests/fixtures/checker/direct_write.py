from pathlib import Path


def persist_outside_gateway(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")
