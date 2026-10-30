from app.core.redis import get_redis
from app.core.config import settings
from decimal import Decimal
from typing import Optional, Literal
import json
import time
import logging

logger = logging.getLogger(__name__)

GuardType = Literal["kill_switch", "rate_limit", "drawdown", "position_limit", "sector_limit"]

GUARD_CONFIGS = {
    "kill_switch": {"enabled": True},
    "rate_limit": {"max_orders_per_minute": 10},
    "drawdown": {"max_daily_drawdown_pct": 2.0},
    "position_limit": {"max_position_pct": 10.0},
    "sector_limit": {"max_sector_pct": 25.0},
}


class ExecutionGuards:
    def __init__(self):
        self._local_cache: dict = {}
    
    async def _get_redis(self):
        return await get_redis()
    
    async def initialize(self):
        redis = await self._get_redis()
        for guard_type, config in GUARD_CONFIGS.items():
            key = f"guard:{guard_type}"
            exists = await redis.exists(key)
            if not exists:
                await redis.hset(key, mapping={
                    "enabled": "1" if config.get("enabled", True) else "0",
                    "config": json.dumps({k: v for k, v in config.items() if k != "enabled"}),
                    "triggered_at": "",
                    "trigger_count": "0",
                })
            else:
                cached = await redis.hgetall(key)
                self._local_cache[guard_type] = {
                    "enabled": cached.get("enabled") == "1",
                    "config": json.loads(cached.get("config", "{}")),
                    "triggered_at": cached.get("triggered_at"),
                    "trigger_count": int(cached.get("trigger_count", "0")),
                }
        logger.info("Execution guards initialized")
    
    async def is_enabled(self, guard_type: GuardType) -> bool:
        if guard_type in self._local_cache:
            return self._local_cache[guard_type]["enabled"]
        redis = await self._get_redis()
        val = await redis.hget(f"guard:{guard_type}", "enabled")
        return val == "1"
    
    async def set_enabled(self, guard_type: GuardType, enabled: bool):
        redis = await self._get_redis()
        await redis.hset(f"guard:{guard_type}", "enabled", "1" if enabled else "0")
        self._local_cache.setdefault(guard_type, {})["enabled"] = enabled
        logger.info(f"Guard {guard_type} {'enabled' if enabled else 'disabled'}")
    
    async def check_pre_trade(
        self,
        symbol: str,
        side: str,
        qty: float,
        current_price: float,
        portfolio_value: float,
        sector: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        if not await self.is_enabled("kill_switch"):
            return False, "Kill switch activated"
        
        if not await self._check_rate_limit():
            return False, "Rate limit exceeded"
        
        if not await self._check_drawdown():
            return False, "Daily drawdown limit exceeded"
        
        if not await self._check_position_limit(symbol, side, qty, current_price, portfolio_value):
            return False, "Position limit exceeded"
        
        if sector and not await self._check_sector_limit(sector, symbol, side, qty, current_price, portfolio_value):
            return False, "Sector limit exceeded"
        
        return True, None
    
    async def _check_rate_limit(self) -> bool:
        if not await self.is_enabled("rate_limit"):
            return True
        redis = await self._get_redis()
        config = await self._get_config("rate_limit")
        max_orders = config.get("max_orders_per_minute", 10)
        
        key = "guard:rate_limit:orders"
        now = time.time()
        await redis.zremrangebyscore(key, 0, now - 60)
        count = await redis.zcard(key)
        
        if count >= max_orders:
            await self._trigger("rate_limit")
            return False
        await redis.zadd(key, {f"{now}": now})
        return True
    
    async def _check_drawdown(self) -> bool:
        if not await self.is_enabled("drawdown"):
            return True
        redis = await self._get_redis()
        config = await self._get_config("drawdown")
        max_dd = config.get("max_daily_drawdown_pct", 2.0)
        
        day_key = time.strftime("account:equity:peak:%Y-%m-%d")
        current_key = "account:equity:current"
        
        peak = await redis.get(day_key)
        if peak is None:
            return True
        
        peak_value = float(peak)
        current = await redis.get(current_key)
        if current is None:
            return True
        
        current_value = float(current)
        dd_pct = ((peak_value - current_value) / peak_value) * 100
        
        if dd_pct >= max_dd:
            await self._trigger("drawdown")
            return False
        return True
    
    async def _check_position_limit(
        self, symbol: str, side: str, qty: float, price: float, portfolio_value: float
    ) -> bool:
        if not await self.is_enabled("position_limit"):
            return True
        config = await self._get_config("position_limit")
        max_pct = config.get("max_position_pct", 10.0)
        
        redis = await self._get_redis()
        pos_key = f"position:{symbol}"
        current_qty = float(await redis.get(pos_key) or 0)
        
        new_qty = current_qty + qty if side == "buy" else current_qty - qty
        position_value = abs(new_qty) * price
        
        if portfolio_value <= 0:
            return False
        position_pct = (position_value / portfolio_value) * 100
        
        return position_pct <= max_pct
    
    async def _check_sector_limit(
        self, sector: str, symbol: str, side: str, qty: float, price: float, portfolio_value: float
    ) -> bool:
        if not await self.is_enabled("sector_limit"):
            return True
        config = await self._get_config("sector_limit")
        max_pct = config.get("max_sector_pct", 25.0)
        
        redis = await self._get_redis()
        sector_key = f"sector:{sector}"
        current_value = float(await redis.get(sector_key) or 0)
        
        position_value = qty * price
        new_value = current_value + position_value if side == "buy" else current_value - position_value
        
        if portfolio_value <= 0:
            return False
        sector_pct = (abs(new_value) / portfolio_value) * 100
        
        return sector_pct <= max_pct
    
    async def update_position(self, symbol: str, side: str, qty: float, price: float, sector: Optional[str] = None):
        redis = await self._get_redis()
        pos_key = f"position:{symbol}"
        
        current_qty = float(await redis.get(pos_key) or 0)
        new_qty = current_qty + qty if side == "buy" else current_qty - qty
        await redis.set(pos_key, str(new_qty))
        
        if sector:
            sector_key = f"sector:{sector}"
            if side == "buy":
                await redis.incrbyfloat(sector_key, qty * price)
            else:
                await redis.incrbyfloat(sector_key, -(qty * price))
    
    async def record_equity(self, equity: float):
        redis = await self._get_redis()
        day_key = time.strftime("account:equity:peak:%Y-%m-%d")
        now = time.time()
        
        prev_peak = await redis.get(day_key)
        if prev_peak is None or equity > float(prev_peak):
            await redis.set(day_key, str(equity), ex=2 * 86400)
        
        await redis.set("account:equity:current", str(equity))
        await redis.zadd("account:equity:history", {str(equity): now})
        await redis.zremrangebyscore("account:equity:history", 0, now - 86400 * 2)
    
    async def _get_config(self, guard_type: GuardType) -> dict:
        redis = await self._get_redis()
        val = await redis.hget(f"guard:{guard_type}", "config")
        return json.loads(val) if val else {}
    
    async def _trigger(self, guard_type: GuardType):
        redis = await self._get_redis()
        key = f"guard:{guard_type}"
        await redis.hincrby(key, "trigger_count", 1)
        await redis.hset(key, "triggered_at", str(time.time()))
        logger.warning(f"Guard triggered: {guard_type}")
    
    async def get_status(self) -> dict:
        redis = await self._get_redis()
        result = {}
        for guard_type in GUARD_CONFIGS:
            data = await redis.hgetall(f"guard:{guard_type}")
            result[guard_type] = {
                "enabled": data.get("enabled") == "1",
                "config": json.loads(data.get("config", "{}")),
                "triggered_at": data.get("triggered_at"),
                "trigger_count": int(data.get("trigger_count", "0")),
            }
        return result


execution_guards = ExecutionGuards()