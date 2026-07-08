from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from testcode.adapters.coze import CozeClient
from testcode.adapters.dify import DifyClient
from testcode.adapters.n8n import N8nClient
from testcode.cache import CachedDifyClient, DifyCache, RedisDifyCache
from testcode.config.settings import AppSettings
from testcode.providers.base import ProviderAdapter


@dataclass(slots=True)
class ProviderRegistry:
    coze: CozeClient
    dify: ProviderAdapter
    n8n: N8nClient

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "ProviderRegistry":
        dify_client: ProviderAdapter = DifyClient(
            api_key=settings.dify.api_key,
            base_url=settings.dify.base_url,
            timeout=settings.dify.timeout_seconds,
        )
        if settings.dify.cache_enabled:
            if settings.dify.cache_backend.lower() == "redis" and settings.dify.cache_redis_url:
                try:
                    import redis

                    redis_client = redis.from_url(settings.dify.cache_redis_url)
                    redis_cache = RedisDifyCache(
                        redis_client=redis_client,
                        prefix=settings.dify.cache_redis_prefix,
                        ttl_seconds=settings.dify.cache_ttl_seconds,
                    )
                    dify_client = CachedDifyClient(client=dify_client, cache=redis_cache)
                except ImportError:
                    file_cache = DifyCache(directory=Path(settings.dify.cache_directory), ttl_seconds=settings.dify.cache_ttl_seconds)
                    dify_client = CachedDifyClient(client=dify_client, cache=file_cache)
                except Exception:
                    file_cache = DifyCache(directory=Path(settings.dify.cache_directory), ttl_seconds=settings.dify.cache_ttl_seconds)
                    dify_client = CachedDifyClient(client=dify_client, cache=file_cache)
            else:
                file_cache = DifyCache(directory=Path(settings.dify.cache_directory), ttl_seconds=settings.dify.cache_ttl_seconds)
                dify_client = CachedDifyClient(client=dify_client, cache=file_cache)

        return cls(
            coze=CozeClient(
                access_token=settings.coze.access_token,
                bot_id=settings.coze.bot_id,
                base_url=settings.coze.base_url,
                timeout=settings.coze.timeout_seconds,
            ),
            dify=dify_client,
            n8n=N8nClient(base_url=settings.n8n.base_url, timeout=settings.n8n.timeout_seconds),
        )

    def get(self, provider: str) -> ProviderAdapter:
        normalized = provider.strip().lower()
        if normalized == "coze":
            return self.coze
        if normalized == "dify":
            return self.dify
        if normalized == "n8n":
            return self.n8n
        raise ValueError(f"Unsupported provider: {provider}")
