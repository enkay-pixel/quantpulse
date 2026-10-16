"""The dashboard reaches the API on its own origin, and the three places that arrange it agree.

The bundle's default API address, the image's build argument and nginx's forwarding rule must
name the same path. When the bundle held an absolute http://localhost:8000 instead, opening the
dashboard at 127.0.0.1 — which Docker Desktop's link does — blocked every request on CORS, and the
page reported the API unreachable while it was healthy.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_bundle_image_and_proxy_all_use_the_same_relative_path() -> None:
    client = (ROOT / "web/src/api/client.ts").read_text()
    dockerfile = (ROOT / "docker/web.Dockerfile").read_text()
    nginx = (ROOT / "docker/nginx.conf").read_text()

    default = re.search(r'VITE_API_URL as string \| undefined\) \?\? "([^"]+)"', client)
    assert default, "could not find the client's default API base"
    assert default.group(1) == "/api", "the dashboard's default API address is not same-origin"
    assert "ARG VITE_API_URL=/api" in dockerfile, "the image builds the bundle with another address"
    assert re.search(r"location /api/ \{", nginx), "nginx does not forward /api"
    assert "proxy_pass $api;" in nginx and "http://api:8000" in nginx


def test_the_proxy_resolves_the_api_per_request() -> None:
    """A literal upstream is resolved once, at startup: nginx then refuses to start while the API
    is down and keeps a stale address after the API container is recreated."""
    nginx = (ROOT / "docker/nginx.conf").read_text()
    assert re.search(r"resolver 127\.0\.0\.11", nginx), "no per-request resolver"
    assert "set $api" in nginx, "upstream is a literal, resolved once at startup"
