from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CozeSettings:
    access_token: str = ""
    bot_id: str = ""
    base_url: str = "https://api.coze.com"
    timeout_seconds: float = 30.0
