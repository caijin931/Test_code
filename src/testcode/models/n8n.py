from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class N8nTriggerResult:
    provider: str = "n8n"
    workflow_url: str = ""
    execution_id: str | None = None
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
