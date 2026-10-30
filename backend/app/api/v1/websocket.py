from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.services.ws_manager import manager
from app.core.security import verify_api_key
from app.services.alpaca_ws import alpaca_ws
from app.schemas import QuoteData, TradeData
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["websocket"])


@router.websocket("/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    api_key: str = Query(...),
):
    from app.core.config import settings
    if api_key != settings.api_secret_key:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    
    client_id = f"client_{id(websocket)}"
    await manager.connect(websocket, client_id)
    
    quote_cb = _make_quote_callback(client_id)
    trade_cb = _make_trade_callback(client_id)
    alpaca_ws.on_quote(quote_cb)
    alpaca_ws.on_trade(trade_cb)
    
    quote_task = asyncio.create_task(_idle(client_id, "quote"))
    trade_task = asyncio.create_task(_idle(client_id, "trade"))
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from {client_id}: {data}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error for {client_id}: {e}")
    finally:
        quote_task.cancel()
        trade_task.cancel()
        alpaca_ws.remove_quote_callback(quote_cb)
        alpaca_ws.remove_trade_callback(trade_cb)
        manager.disconnect(client_id)


def _make_quote_callback(client_id: str):
    async def callback(quote: QuoteData):
        await manager.send_personal(client_id, {"type": "quote", "data": quote.model_dump()})
    return callback


def _make_trade_callback(client_id: str):
    async def callback(trade: TradeData):
        await manager.send_personal(client_id, {"type": "trade", "data": trade.model_dump()})
    return callback


async def _idle(client_id: str, kind: str):
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


@router.get("/quotes", dependencies=[Depends(verify_api_key)])
async def get_quotes(symbols: str = "AAPL,NVDA,SPY,QQQ,MSFT,GOOGL,AMZN,META,TSLA,JPM"):
    from app.services.alpaca_rest import alpaca_rest
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    return await alpaca_rest.get_latest_quotes(symbol_list)