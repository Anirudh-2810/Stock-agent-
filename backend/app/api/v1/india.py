import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/india", tags=["india"])


class PaperOrderRequest(BaseModel):
    symbol: str = Field(..., examples=["RELIANCE.NS"])
    side: str = Field(..., description="buy | sell")
    qty: float = Field(..., gt=0)
    strategy: str = "manual"
    comment: str = ""


class LLMExplainRequest(BaseModel):
    text: str
    model: Optional[str] = None


@router.post("/orders")
async def paper_order(req: PaperOrderRequest):
    from app.services.india_paper import india_paper

    result = await india_paper.market_order(
        symbol=req.symbol.upper(), side=req.side, qty=req.qty,
        strategy=req.strategy, comment=req.comment,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "order rejected"))
    return result


@router.get("/positions")
async def paper_positions():
    from app.services.india_paper import india_paper

    return {"paper_only": True, "positions": await india_paper.positions_snapshot()}


@router.get("/account")
async def paper_account():
    from app.services.india_paper import india_paper

    pos = await india_paper.positions_snapshot()
    prices = {p["symbol"]: p["current_price"] for p in pos}
    return india_paper.account_summary(prices)


@router.get("/option-chain/straddle")
async def straddle_idea(symbol: str = "NIFTY"):
    from app.services.options_premium import options_premium

    return options_premium.straddle_wrap(symbol.upper())


@router.get("/option-chain/status")
async def options_status():
    from app.services.options_premium import options_premium

    return options_premium.status()


@router.post("/llm/explain")
async def llm_explain(req: LLMExplainRequest):
    from app.services.llm_client import llm_client

    ok = await llm_client.available()
    if not ok:
        return {"available": False, "hint": "start OmniRoute gateway or set LLM_BASE_URL/LLM_API_KEY"}
    result = await llm_client.chat(
        messages=[
            {
                "role": "user",
                "content": (
                    "You are a trading-desk analyst. Explain the following to the user in "
                    "3-4 bullet points, flagging any risk in plain language. Never give "
                    "guarantees.\n\n" + req.text
                ),
            }
        ],
        model=req.model,
    )
    return result
