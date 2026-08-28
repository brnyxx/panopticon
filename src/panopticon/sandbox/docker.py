"""Docker runtime implementation using argument vectors only."""

from __future__ import annotations

import re

from ._docker_container import DockerContainer
from ._docker_runtime import DockerRuntime

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_pinned_image(image: str) -> bool:
    return _DIGEST.fullmatch(image) is not None or (
        "@sha256:" in image and _DIGEST.fullmatch(image.rsplit("@", 1)[1]) is not None
    )


__all__ = ["DockerContainer", "DockerRuntime", "is_pinned_image"]
