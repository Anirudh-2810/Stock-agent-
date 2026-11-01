from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import verify_api_key
from app.services.alpaca_rest import alpaca_rest
from app.services.execution_guards import execution_guards
from app.schemas import (
    OrderRequest, OrderResponse, PositionResponse, AccountResponse,
    FillResponse, GuardStatus, GuardUpdate, KillSwitchRequest
)
from app.models import Order, Position, Fill, AccountSnapshot, Ticker
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
import asyncio
import logging
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["trading"])


async def _track_order_fill(client_order_id, symbol: str, side: str, qty: float, price: float) -> None:
    if not client_order_id:
        return
    try:
        for _ in range(30):
            order = await alpaca_rest.get_order_by_client_id(client_order_id)
            status = str(getattr(order, "status", "") or "")
            if status in ("FILLED", "CANCELED", "REJECTED", "EXPIRED", "DENIED"):
                filled_qty = float(getattr(order, "filled_qty", None) or 0)
                if status == "FILLED" and filled_qty > 0:
                    await execution_guards.update_position(
                        symbol=symbol, side=side, qty=filled_qty, price=price
                    )
                break
            await asyncio.sleep(2)
    except Exception as e:
        logger.warning(f"Order fill tracking failed for {client_order_id}: {e}")


@router.get("/account", response_model=AccountResponse, dependencies=[Depends(verify_api_key)])
async def get_account():
    return await alpaca_rest.get_account()


@router.get("/positions", response_model=List[PositionResponse], dependencies=[Depends(verify_api_key)])
async def get_positions():
    return await alpaca_rest.get_positions()


@router.post("/orders", response_model=OrderResponse, dependencies=[Depends(verify_api_key)])
async def place_order(order: OrderRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    from app.services.alpaca_ws import alpaca_ws
    
    quotes = await alpaca_rest.get_latest_quotes([order.symbol])
    if not quotes:
        raise HTTPException(status_code=400, detail="No quote available for symbol")
    
    current_price = (quotes[0].bid_price + quotes[0].ask_price) / 2
    account = await alpaca_rest.get_account()
    
    sector = None
    try:
        result = await db.execute(select(Ticker).where(Ticker.symbol == order.symbol))
        tkr = result.scalars().first()
        sector = tkr.sector if tkr else None
    except Exception:
        sector = None

    allowed, reason = await execution_guards.check_pre_trade(
        symbol=order.symbol,
        side=order.side,
        qty=float(order.qty),
        current_price=float(current_price),
        portfolio_value=float(account.portfolio_value),
        sector=sector,
    )
    
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Guard blocked: {reason}")
    
    result = await alpaca_rest.place_order(order)
    
    background_tasks.add_task(
        _track_order_fill,
        getattr(result, "client_order_id", None),
        order.symbol, order.side, float(order.qty), float(current_price),
    )
    background_tasks.add_task(execution_guards.record_equity, float(account.equity))
    
    return result


@router.get("/orders", response_model=List[OrderResponse], dependencies=[Depends(verify_api_key)])
async def get_orders(status: Optional[str] = None, limit: int = 100):
    return await alpaca_rest.get_orders(status, limit)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_order(order_id: str):
    success = await alpaca_rest.cancel_order(order_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to cancel order")
    return {"success": True}


@router.post("/positions/{symbol}/close", dependencies=[Depends(verify_api_key)])
async def close_position(symbol: str):
    success = await alpaca_rest.close_position(symbol)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to close position")
    await execution_guards.clear_position(symbol)
    return {"success": True}


@router.post("/positions/close-all", dependencies=[Depends(verify_api_key)])
async def close_all_positions():
    success = await alpaca_rest.close_all_positions()
    if not success:
        raise HTTPException(status_code=400, detail="Failed to close all positions")
    positions = await alpaca_rest.get_positions()
    symbols = [p.symbol for p in positions if p.symbol]
    await execution_guards.clear_positions(symbols)
    return {"success": True}


@router.get("/guards", response_model=dict, dependencies=[Depends(verify_api_key)])
async def get_guards():
    return await execution_guards.get_status()


@router.post("/guards/{guard_type}", response_model=dict, dependencies=[Depends(verify_api_key)])
async def update_guard(guard_type: str, update: GuardUpdate):
    if guard_type not in ["kill_switch", "rate_limit", "drawdown", "position_limit", "sector_limit"]:
        raise HTTPException(status_code=400, detail="Invalid guard type")
    await execution_guards.set_enabled(guard_type, update.is_active)
    return {"success": True, "guard_type": guard_type, "enabled": update.is_active}


@router.post("/kill-switch", dependencies=[Depends(verify_api_key)])
async def kill_switch(request: KillSwitchRequest):
    await execution_guards.set_enabled("kill_switch", request.activate)
    return {"success": True, "activated": request.activate}