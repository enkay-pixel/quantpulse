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


# --- the browser on this machine is a caller too ---------------------------------------------
#
# Binding to 127.0.0.1 keeps the LAN out, but a web page open in this machine's browser can still
# send requests to 127.0.0.1, by cross-origin calls or by DNS rebinding (a hostile name re-pointed
# at 127.0.0.1). MLflow and Dagster have no authentication, and the pipeline loads whatever the
# registry's @champion names. Found in the 2026-10-22 security review: MLflow allowed every host
# and origin, and Dagster checked neither.


def _mlflow_command() -> str:
    return (ROOT / "docker" / "mlflow.Dockerfile").read_text()


def test_mlflow_keeps_its_host_and_origin_checks() -> None:
    command = _mlflow_command()
    hosts = re.search(r"--allowed-hosts '([^']*)'", command)
    origins = re.search(r"--cors-allowed-origins '([^']*)'", command)
    assert hosts and origins, "MLflow must name its allowed hosts and origins explicitly"
    assert "*" not in hosts.group(1) and "*" not in origins.group(1), (
        "a wildcard admits any website"
    )
    assert "--disable-security-middleware" not in command
    # The pipeline reaches MLflow by its service name; without it every run fails to log a model.
    assert "mlflow:5000" in hosts.group(1).split(",")


def test_dagster_is_published_only_through_the_host_check() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    assert "ports" not in services["dagster-webserver"], "published directly, it skips the check"
    assert "127.0.0.1:3000:3000" in services["web"]["ports"]


def test_nginx_refuses_any_host_but_this_machines_own_names_on_the_dagster_port() -> None:
    conf = (ROOT / "docker" / "nginx.conf").read_text()
    default = re.search(r"listen 3000 default_server;\s*server_name _;[^}]*return 421;", conf)
    assert default, "an unknown Host on port 3000 must be refused, not proxied"
    named = re.search(r"listen 3000;\s*server_name ([^;]*);", conf)
    assert named and set(named.group(1).split()) == {"localhost", "127.0.0.1"}
