# Redis client with mock fallback for development
import sys
from typing import Any, Optional, List, Dict
from app.core.config import settings

# Try to import redis, fall back to mock if not available or connection fails
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

# Mock Redis implementation for development
class MockRedis:
    """In-memory Redis mock for development when Redis server is not available."""
    
    def __init__(self):
        self._data: Dict[str, str] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._sets: Dict[str, set] = {}
        self._zsets: Dict[str, Dict[str, float]] = {}
        self._pubsub_channels: Dict[str, List[asyncio.Queue]] = {}
        self._expires: Dict[str, float] = {}
    
    async def close(self):
        pass
    
    async def ping(self):
        return True
    
    # String operations
    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)
    
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        self._data[key] = str(value)
        if ex:
            import time
            self._expires[key] = time.time() + ex
        return True
    
    async def exists(self, key: str) -> int:
        return 1 if key in self._data else 0
    
    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count
    
    async def incrbyfloat(self, key: str, amount: float) -> float:
        current = float(self._data.get(key, "0"))
        new_val = current + float(amount)
        self._data[key] = str(new_val)
        return new_val
    
    # Hash operations
    async def hset(self, name: str, mapping: Optional[Dict[str, str]] = None, **kwargs) -> int:
        if name not in self._hashes:
            self._hashes[name] = {}
        count = 0
        if mapping:
            for k, v in mapping.items():
                if k not in self._hashes[name]:
                    count += 1
                self._hashes[name][k] = str(v)
        for k, v in kwargs.items():
            if k not in self._hashes[name]:
                count += 1
            self._hashes[name][k] = str(v)
        return count
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        return self._hashes.get(name, {}).get(key)
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        return self._hashes.get(name, {})
    
    async def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        if name not in self._hashes:
            self._hashes[name] = {}
        current = int(self._hashes[name].get(key, "0"))
        new_val = current + amount
        self._hashes[name][key] = str(new_val)
        return new_val
    
    # Set operations
    async def sadd(self, name: str, *values: str) -> int:
        if name not in self._sets:
            self._sets[name] = set()
        count = 0
        for v in values:
            if v not in self._sets[name]:
                self._sets[name].add(v)
                count += 1
        return count
    
    async def smembers(self, name: str) -> set:
        return self._sets.get(name, set())
    
    # Sorted set operations
    async def zadd(self, name: str, mapping: Dict[str, float]) -> int:
        if name not in self._zsets:
            self._zsets[name] = {}
        count = 0
        for k, v in mapping.items():
            if k not in self._zsets[name]:
                count += 1
            self._zsets[name][k] = float(v)
        return count
    
    async def zrem(self, name: str, *values: str) -> int:
        if name not in self._zsets:
            return 0
        count = 0
        for v in values:
            if v in self._zsets[name]:
                del self._zsets[name][v]
                count += 1
        return count
    
    async def zrangebyscore(self, name: str, min_val: float, max_val: float, 
                            start: int = 0, num: int = -1, withscores: bool = False) -> List:
        if name not in self._zsets:
            return []
        items = [(k, v) for k, v in self._zsets[name].items() 
                 if min_val <= v <= max_val]
        items.sort(key=lambda x: x[1])
        items = items[start:start+num] if num > 0 else items[start:]
        if withscores:
            return items
        return [k for k, _ in items]
    
    async def zrevrangebyscore(self, name: str, max_val: float, min_val: float,
                               start: int = 0, num: int = -1, withscores: bool = False) -> List:
        if name not in self._zsets:
            return []
        items = [(k, v) for k, v in self._zsets[name].items() 
                 if min_val <= v <= max_val]
        items.sort(key=lambda x: x[1], reverse=True)
        items = items[start:start+num] if num > 0 else items[start:]
        if withscores:
            return items
        return [k for k, _ in items]
    
    async def zcard(self, name: str) -> int:
        return len(self._zsets.get(name, {}))
    
    async def zremrangebyscore(self, name: str, min_val: float, max_val: float) -> int:
        if name not in self._zsets:
            return 0
        to_remove = [k for k, v in self._zsets[name].items() if min_val <= v <= max_val]
        for k in to_remove:
            del self._zsets[name][k]
        return len(to_remove)
    
    # Pub/Sub
    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._pubsub_channels:
            self._pubsub_channels[channel] = []
        for queue in self._pubsub_channels[channel]:
            await queue.put(message)
        return len(self._pubsub_channels[channel])
    
    def pubsub(self):
        return MockPubSub(self)

# Mock PubSub
class MockPubSub:
    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._channels: List[str] = []
        self._queue: asyncio.Queue = asyncio.Queue()
    
    async def subscribe(self, *channels: str):
        for channel in channels:
            if channel not in self._channels:
                self._channels.append(channel)
                if channel not in self._redis._pubsub_channels:
                    self._redis._pubsub_channels[channel] = []
                queue = asyncio.Queue()
                self._redis._pubsub_channels[channel].append(queue)
                self._queue = queue  # Use last subscribed channel's queue
    
    async def unsubscribe(self, *channels: str):
        for channel in channels:
            if channel in self._channels:
                self._channels.remove(channel)
    
    async def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = 1.0):
        try:
            import asyncio
            msg = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return {
                "type": "message",
                "channel": self._channels[0] if self._channels else "",
                "data": msg
            }
        except asyncio.TimeoutError:
            return None
    
    async def close(self):
        pass


# Global Redis client instance
_redis_client = None
_mock_redis = None


async def get_redis():
    """Get Redis client; fail closed in production, mock only in development."""
    global _redis_client, _mock_redis

    if settings.environment == "production":
        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis client library unavailable in production")
        if _redis_client is None:
            _redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            await _redis_client.ping()
        return _redis_client

    # Development fallback to mock
    if REDIS_AVAILABLE and _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            await _redis_client.ping()
            return _redis_client
        except Exception as e:
            print("Real Redis unavailable, falling back to mock: " + str(e))
            _redis_client = None

    if _mock_redis is None:
        _mock_redis = MockRedis()
    return _mock_redis
    # Try real Redis first if available
    if REDIS_AVAILABLE and _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            # Test connection
            await _redis_client.ping()
            return _redis_client
        except Exception as e:
            print(f"Real Redis unavailable, falling back to mock: {e}")
            _redis_client = None
    
    # Fall back to mock
    if _mock_redis is None:
        _mock_redis = MockRedis()
    return _mock_redis


async def close_redis() -> None:
    global _redis_client, _mock_redis
    if _redis_client:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None
    _mock_redis = None


# Import asyncio at module level for mock
import asyncio
