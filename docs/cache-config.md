# Cache Configuration

## File cache

```yaml
dify:
  cache_enabled: true
  cache_backend: file
  cache_directory: .cache/dify
  cache_ttl_seconds: 86400
```

## Redis cache

```yaml
dify:
  cache_enabled: true
  cache_backend: redis
  cache_redis_url: redis://localhost:6379/0
  cache_redis_prefix: testcode:dify
  cache_ttl_seconds: 86400
```

## Fallback behavior

If Redis cache initialization fails, the provider registry falls back to file cache automatically.

## Disable cache

```yaml
dify:
  cache_enabled: false
```
