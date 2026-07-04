from __future__ import annotations

from pathlib import Path

from testcode.config.settings import AppSettings
from testcode.orchestrator import Orchestrator


def build_orchestrator(settings_path: str | Path | None = None, env_prefix: str = "TESTCODE_") -> Orchestrator:
    settings = AppSettings.load(settings_path, prefix=env_prefix)
    return Orchestrator.from_settings(settings)
