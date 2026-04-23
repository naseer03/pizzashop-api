"""Lightweight cache with optional Redis; falls back to in-process TTL entries."""

from __future__ import annotations

import json
import time
from typing import Any

from app.config import settings

_redis = None


def _get_redis():
    global _redis
    if _redis is False:
        return None
    if _redis is not None:
        return _redis
    if not settings.redis_url:
        _redis = False
        return None
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis = client
        return _redis
    except Exception:
        _redis = False
        return None


_mem: dict[str, tuple[float, str]] = {}


def cache_get_json(key: str) -> Any | None:
    r = _get_redis()
    if r:
        raw = r.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    now = time.time()
    hit = _mem.get(key)
    if not hit:
        return None
    exp_at, payload = hit
    if exp_at < now:
        del _mem[key]
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    payload = json.dumps(value, default=str)
    r = _get_redis()
    if r:
        r.setex(key, ttl_seconds, payload)
        return
    _mem[key] = (time.time() + ttl_seconds, payload)


def cache_delete(key: str) -> None:
    r = _get_redis()
    if r:
        r.delete(key)
        return
    _mem.pop(key, None)
