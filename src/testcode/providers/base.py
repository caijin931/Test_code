from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from testcode.models.provider_result import ProviderResult


class ProviderAdapter(ABC):
    @abstractmethod
    def chat(self, *args: Any, **kwargs: Any) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def run_workflow(self, *args: Any, **kwargs: Any) -> ProviderResult:
        raise NotImplementedError
