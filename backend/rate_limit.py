import math
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, DefaultDict, Dict, Tuple

from fastapi import HTTPException, Request, Response


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


class InMemoryRateLimiter:
    """
    Small per-process sliding-window limiter.

    This is a practical first pass for a single backend instance. It will not
    coordinate across multiple workers or servers, but it gives us immediate
    protection against repeated bursts hitting one process.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: DefaultDict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def evaluate(self, client_key: str, policy: RateLimitPolicy) -> Dict[str, int]:
        now = time.monotonic()
        window_start = now - policy.window_seconds
        storage_key = (policy.name, client_key)

        with self._lock:
            timestamps = self._events[storage_key]
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= policy.limit:
                retry_after = max(1, math.ceil(policy.window_seconds - (now - timestamps[0])))
                return {
                    "allowed": 0,
                    "limit": policy.limit,
                    "remaining": 0,
                    "retry_after": retry_after,
                }

            timestamps.append(now)
            remaining = max(0, policy.limit - len(timestamps))
            return {
                "allowed": 1,
                "limit": policy.limit,
                "remaining": remaining,
                "retry_after": 0,
            }


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def build_policy(name: str, default_limit: int, default_window_seconds: int) -> RateLimitPolicy:
    env_prefix = name.upper().replace("-", "_")
    return RateLimitPolicy(
        name=name,
        limit=_env_int(f"RATE_LIMIT_{env_prefix}_LIMIT", default_limit),
        window_seconds=_env_int(f"RATE_LIMIT_{env_prefix}_WINDOW_SECONDS", default_window_seconds),
    )


def client_identifier(request: Request) -> str:
    cf_connecting_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_connecting_ip:
        return cf_connecting_ip

    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def rate_limit_dependency(policy: RateLimitPolicy, limiter: InMemoryRateLimiter):
    def dependency(request: Request, response: Response) -> None:
        client_key = client_identifier(request)
        decision = limiter.evaluate(client_key=client_key, policy=policy)

        response.headers["X-RateLimit-Limit"] = str(decision["limit"])
        response.headers["X-RateLimit-Remaining"] = str(decision["remaining"])
        response.headers["X-RateLimit-Policy"] = f"{policy.limit};w={policy.window_seconds}"

        if not decision["allowed"]:
            headers = {
                "Retry-After": str(decision["retry_after"]),
                "X-RateLimit-Limit": str(decision["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Policy": f"{policy.limit};w={policy.window_seconds}",
            }
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please wait and try again.",
                headers=headers,
            )

    return dependency
