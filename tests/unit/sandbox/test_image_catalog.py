from pathlib import Path

import pytest

from panopticon.sandbox.image_catalog import (
    ImageCatalog,
    ImageStatus,
    parse_image_lock,
)

LOCK = Path(__file__).parents[3] / "src/panopticon/sandbox/images.lock"


def test_four_published_identities_are_digest_qualified() -> None:
    catalog = ImageCatalog.from_lock(LOCK)
    assert catalog.select("npm", "20").reference.endswith(
        "ghcr.io/brnyxx/pano-sandbox-node:20@sha256:2ef58b44bd9ebc247e97d1b3c54f63570ae206b925b277d86d93e5319d1cd367"
    )
    assert catalog.select("npm", 22).status is ImageStatus.SUPPORTED
    assert catalog.select("python", "3.12").status is ImageStatus.SUPPORTED
    assert catalog.select("generic", "base").status is ImageStatus.SUPPORTED


@pytest.mark.parametrize(
    "text",
    [
        "version = 1\n"
        + "\n".join(
            f"{name} = sha256:{'0' * 64}"
            for name in (
                "ghcr.io/brnyxx/pano-sandbox-base:0.1",
                "ghcr.io/brnyxx/pano-sandbox-node:20",
                "ghcr.io/brnyxx/pano-sandbox-node:22",
            )
        ),
        "version = 1\nghcr.io/brnyxx/pano-sandbox-base:0.1 = sha256:not-a-digest",
    ],
)
def test_missing_or_malformed_lock_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_image_lock(text)


def test_duplicate_and_unsupported_selection() -> None:
    text = LOCK.read_text() + "\nghcr.io/brnyxx/pano-sandbox-node:20 = sha256:" + "0" * 64
    with pytest.raises(ValueError):
        parse_image_lock(text)
    catalog = ImageCatalog.from_lock(LOCK)
    assert catalog.select("docker", "20").status is ImageStatus.UNSUPPORTED
    assert catalog.select("npm", "18").status is ImageStatus.UNSUPPORTED
