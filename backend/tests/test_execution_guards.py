import asyncio

from app.services.execution_guards import GUARD_CONFIGS, execution_guards


def _run(coro):
    return asyncio.run(coro)


def _arm_kill_switch(enabled: bool) -> None:
    execution_guards._local_cache["kill_switch"] = {
        "enabled": enabled,
        "config": {},
        "triggered_at": None,
        "trigger_count": 0,
    }


def test_kill_switch_defaults_to_disabled():
    assert GUARD_CONFIGS["kill_switch"]["enabled"] is False


def test_kill_switch_blocks_when_armed():
    async def scenario():
        _arm_kill_switch(True)
        return await execution_guards.check_pre_trade(
            symbol="AAPL", side="buy", qty=1.0, current_price=100.0, portfolio_value=10_000.0
        )

    allowed, reason = _run(scenario())
    assert allowed is False
    assert reason is not None and "Kill switch" in reason


def test_kill_switch_allows_when_disarmed():
    async def scenario():
        _arm_kill_switch(False)
        return await execution_guards.check_pre_trade(
            symbol="AAPL", side="buy", qty=1.0, current_price=100.0, portfolio_value=10_000.0
        )

    allowed, reason = _run(scenario())
    assert allowed is True
    assert reason is None
