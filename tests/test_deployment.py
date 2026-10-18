from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_server_uses_standard_asyncio_loop():
    requirements = (ROOT / "requirements.txt").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "uvicorn[standard]" not in requirements
    assert '"--loop", "asyncio"' in dockerfile


def test_bark_request_paths_are_not_persisted_to_logs():
    compose = (ROOT / "docker-compose.yml").read_text()
    gateway = (ROOT / "deploy/bark-gateway.conf").read_text()
    bark_core = re.search(r"^  bark-core:\n(?P<body>.*?)(?=^  \S)", compose, re.MULTILINE | re.DOTALL)

    assert bark_core is not None
    assert 'driver: "none"' in bark_core.group("body")
    assert "access_log off;" in gateway
