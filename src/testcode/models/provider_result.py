from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderMessage:
    role: str
    content: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResult:
    provider: str
    kind: str
    content: str
    messages: list[ProviderMessage] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
