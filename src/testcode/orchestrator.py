from __future__ import annotations

from dataclasses import dataclass

from testcode.config.settings import AppSettings
from testcode.providers.registry import ProviderRegistry


@dataclass(slots=True)
class Orchestrator:
    """Coordinate provider-specific automation flows."""

    registry: ProviderRegistry | None = None

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "Orchestrator":
        return cls(registry=ProviderRegistry.from_settings(settings))

    def health_check(self) -> dict[str, str]:
        return {"status": "ok", "stack": "python", "providers": "n8n,dify,coze"}

    def provider(self, name: str):
        if self.registry is None:
            raise RuntimeError("Provider registry is not configured")
        return self.registry.get(name)
