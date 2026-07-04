from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DifyCacheSettings:
    enabled: bool = True
    directory: str = ".cache/dify"
    ttl_seconds: int = 86400
