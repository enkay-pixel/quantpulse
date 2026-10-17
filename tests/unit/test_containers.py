"""The containers report whether they work, and build from images that cannot change underneath.

The web container once showed "Up" for minutes while nginx sat stuck before starting, and
`compose up --wait` reported success; only the README screenshots, nine copies of Chrome's error
page, showed it. A container without a health check can fail like that unseen, so every service
declares one. And an image tag on Docker Hub is rebuilt in place, so a base named only by tag is
not the image that was tested: each is pinned by digest as well.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_every_service_reports_its_health() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    missing = [name for name, svc in compose["services"].items() if "healthcheck" not in svc]
    assert not missing, f"give these a healthcheck that proves they work, not just run: {missing}"


def test_docker_hub_bases_are_pinned_by_digest() -> None:
    """A base without a registry host comes from Docker Hub, where tags are rebuilt in place.

    mlflow's image is the exception, and must stay one: its tag is kept equal to the locked client
    by check_tool_pins.py, and with a digest beside it Docker would build the digest and ignore a
    bumped tag, so the check would pass while the old server shipped. Its release tags are not
    rebuilt, so the exact version already pins it.
    """
    for dockerfile in sorted((ROOT / "docker").glob("*.Dockerfile")):
        for line in dockerfile.read_text().splitlines():
            if not line.startswith("FROM "):
                continue
            image = line.split()[1]
            if image.startswith("ghcr.io/mlflow/"):
                assert "@sha256:" not in image, f"{dockerfile.name}: see the docstring"
                continue
            assert re.search(r":[^@]+@sha256:[0-9a-f]{64}$", image), (
                f"{dockerfile.name}: pin {image} by tag and digest"
            )
