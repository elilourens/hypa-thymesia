"""Rate limiting utilities for API endpoints.

This module provides a flexible rate limiting system that can use either
in-memory storage (default) or Redis (when configured).

For production deployments with multiple instances, configure Redis via
the RATE_LIMIT_REDIS_URL environment variable.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Optional
from fastapi import HTTPException

# In-memory rate limiting storage (default backend)
_memory_rate_limits = defaultdict(list)

# Redis client (lazy loaded when configured)
_redis_client = None


def _get_redis_client():
    """Get or initialize Redis client if configured."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            from core.config import settings

            redis_url = getattr(settings, 'rate_limit_redis_url', None)
            if redis_url:
                _redis_client = redis.from_url(redis_url, decode_responses=True)
                _redis_client.ping()  # Test connection
                return _redis_client
        except Exception:
            pass
    return _redis_client


def _check_rate_limit_memory(key: str, limit: int, window: int = 60) -> bool:
    """Check rate limit using in-memory storage.

    Args:
        key: Identifier to rate limit (e.g., user_id)
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        True if request is allowed, False if limit exceeded
    """
    current_time = time.time()

    # Clean up old requests
    _memory_rate_limits[key] = [
        req_time for req_time in _memory_rate_limits[key]
        if current_time - req_time < window
    ]

    # Check if exceeded
    if len(_memory_rate_limits[key]) >= limit:
        return False

    # Record request
    _memory_rate_limits[key].append(current_time)
    return True


def _check_rate_limit_redis(key: str, limit: int, window: int = 60) -> bool:
    """Check rate limit using Redis.

    Args:
        key: Identifier to rate limit (e.g., user_id)
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        True if request is allowed, False if limit exceeded
    """
    redis_client = _get_redis_client()
    if not redis_client:
        return True  # Fail open if Redis is not available

    redis_key = f"rate_limit:{key}"

    try:
        current_count = redis_client.incr(redis_key)

        # Set expiration on first request
        if current_count == 1:
            redis_client.expire(redis_key, window)

        return current_count <= limit
    except Exception:
        return True  # Fail open on Redis errors


def check_rate_limit(key: str, limit: int, window: int = 60) -> bool:
    """Check rate limit using configured backend (Redis or in-memory).

    Args:
        key: Identifier to rate limit (e.g., user_id)
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        True if request is allowed, False if limit exceeded
    """
    redis_client = _get_redis_client()

    if redis_client:
        return _check_rate_limit_redis(key, limit, window)
    else:
        return _check_rate_limit_memory(key, limit, window)


def rate_limit(calls_per_minute: int = 60):
    """
    Decorator for rate limiting API endpoints by user.

    Limits requests per authenticated user. Works with both in-memory
    storage and Redis backends.

    Args:
        calls_per_minute: Number of calls allowed per minute per user

    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded

    Usage:
        @rate_limit(calls_per_minute=100)
        async def my_endpoint(current_user: AuthUser = Depends(get_current_user)):
            ...

    Note:
        To use Redis, set RATE_LIMIT_REDIS_URL environment variable.
        Example: redis://localhost:6379
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get('current_user')
            if not current_user:
                # Proceed without rate limiting if no auth user
                return await func(*args, **kwargs)

            user_id = current_user.id

            # Check rate limit
            if not check_rate_limit(user_id, calls_per_minute, window=60):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {calls_per_minute} requests per minute."
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
