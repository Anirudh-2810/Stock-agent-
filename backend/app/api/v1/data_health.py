from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from sqlalchemy.dialects.postgresql import insert
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
import asyncio

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models import OHLCV, CorporateAction, Ticker
from app.services.sec_parser import tag_resolver
from app.tasks.scheduler import scheduler

router = APIRouter(prefix="/api/v1/data", tags=["data-health"], dependencies=[Depends(verify_api_key)])


@router.get("/health/summary")
async def data_health_summary(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    ohlcv_stats = await db.execute(
        select(
            func.count(OHLCV.symbol.distinct()).label("symbols"),
            func.count().label("total_bars"),
            func.max(OHLCV.time).label("latest_bar"),
            func.max(OHLCV.ingestion_timestamp).label("latest_ingestion"),
        ).where(OHLCV.time >= week_ago)
    )
    ohlcv = ohlcv_stats.first()
    
    ca_stats = await db.execute(
        select(
            func.count(CorporateAction.symbol.distinct()).label("symbols"),
            func.count().label("total_actions"),
            func.max(CorporateAction.ex_date).label("latest_ex_date"),
        ).where(CorporateAction.created_at >= week_ago)
    )
    ca = ca_stats.first()
    
    scheduler_jobs = []
    for job in scheduler.get_jobs():
        scheduler_jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    
    return {
        "timestamp": now.isoformat(),
        "ohlcv": {
            "symbols_with_data": ohlcv.symbols or 0,
            "total_bars_7d": ohlcv.total_bars or 0,
            "latest_bar": ohlcv.latest_bar.isoformat() if ohlcv.latest_bar else None,
            "latest_ingestion": ohlcv.latest_ingestion.isoformat() if ohlcv.latest_ingestion else None,
            "ingestion_lag_hours": (
                (now - ohlcv.latest_ingestion).total_seconds() / 3600
            ) if ohlcv.latest_ingestion else None,
        },
        "corporate_actions": {
            "symbols_with_actions": ca.symbols or 0,
            "total_actions_7d": ca.total_actions or 0,
            "latest_ex_date": ca.latest_ex_date.isoformat() if ca.latest_ex_date else None,
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs": scheduler_jobs,
        },
    }


@router.get("/health/ohlcv/{symbol}")
async def ohlcv_health(
    symbol: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    stats = await db.execute(
        select(
            func.count().label("bars"),
            func.min(OHLCV.time).label("first_bar"),
            func.max(OHLCV.time).label("last_bar"),
            func.max(OHLCV.ingestion_timestamp).label("latest_ingestion"),
            func.avg(OHLCV.volume).label("avg_volume"),
        ).where(
            and_(
                OHLCV.symbol == symbol.upper(),
                OHLCV.time >= cutoff,
            )
        )
    )
    row = stats.first()
    
    gaps = await db.execute(
        text("""
            WITH expected AS (
                SELECT generate_series(
                    date_trunc('day', :cutoff)::date,
                    (SELECT max(time)::date FROM ohlcv WHERE symbol = :symbol),
                    '1 day'
                )::date AS trade_date
            ),
            actual AS (
                SELECT time::date AS trade_date FROM ohlcv WHERE symbol = :symbol
            )
            SELECT count(*) as missing_days
            FROM expected e
            LEFT JOIN actual a ON e.trade_date = a.trade_date
            WHERE a.trade_date IS NULL
        """),
        {"symbol": symbol.upper(), "cutoff": cutoff},
    )
    gap_row = gaps.first()
    
    return {
        "symbol": symbol.upper(),
        "period_days": days,
        "bars_found": row.bars or 0,
        "first_bar": row.first_bar.isoformat() if row.first_bar else None,
        "last_bar": row.last_bar.isoformat() if row.last_bar else None,
        "latest_ingestion": row.latest_ingestion.isoformat() if row.latest_ingestion else None,
        "avg_volume": float(row.avg_volume) if row.avg_volume else 0,
        "missing_trading_days": gap_row.missing_days or 0,
        "data_complete": (gap_row.missing_days or 0) == 0,
    }


@router.get("/health/fundamentals")
async def fundamentals_health(db: AsyncSession = Depends(get_db)):
    from app.models import FundamentalsPointInTime
    
    stats = await db.execute(
        select(
            func.count(FundamentalsPointInTime.symbol.distinct()).label("symbols"),
            func.count().label("total_filings"),
            func.max(FundamentalsPointInTime.filing_date).label("latest_filing"),
            func.max(FundamentalsPointInTime.knowledge_timestamp).label("latest_knowledge"),
        )
    )
    row = stats.first()
    
    coverage = await db.execute(
        text("""
            SELECT
                symbol,
                count(*) as filings,
                max(filing_date) as latest_filing,
                count(net_income) as has_net_income,
                count(revenue) as has_revenue,
                count(total_assets) as has_assets,
                count(shares_outstanding) as has_shares
            FROM fundamentals_point_in_time
            GROUP BY symbol
            ORDER BY symbol
        """)
    )
    coverage_rows = coverage.all()
    
    return {
        "total_symbols": row.symbols or 0,
        "total_filings": row.total_filings or 0,
        "latest_filing": row.latest_filing.isoformat() if row.latest_filing else None,
        "latest_knowledge_ts": row.latest_knowledge.isoformat() if row.latest_knowledge else None,
        "coverage": [
            {
                "symbol": r.symbol,
                "filings": r.filings,
                "latest_filing": r.latest_filing.isoformat() if r.latest_filing else None,
                "metrics_present": {
                    "net_income": r.has_net_income,
                    "revenue": r.has_revenue,
                    "total_assets": r.has_assets,
                    "shares_outstanding": r.has_shares,
                },
            }
            for r in coverage_rows
        ],
    }


@router.get("/health/features")
async def features_health(db: AsyncSession = Depends(get_db)):
    try:
        stats = await db.execute(
            text("""
                SELECT
                    count(DISTINCT symbol) as symbols,
                    count(*) as total_rows,
                    max(as_of_date) as latest_date,
                    max(knowledge_timestamp) as latest_knowledge,
                    count(CASE WHEN rsi_14 IS NOT NULL THEN 1 END) as has_rsi,
                    count(CASE WHEN macd_hist IS NOT NULL THEN 1 END) as has_macd,
                    count(CASE WHEN fwd_ret_4w IS NOT NULL THEN 1 END) as has_labels
                FROM ml_features_weekly
            """)
        )
        row = stats.first()
        
        freshness = await db.execute(
            text("""
                SELECT
                    symbol,
                    max(as_of_date) as latest_date,
                    count(*) as weeks
                FROM ml_features_weekly
                GROUP BY symbol
                ORDER BY symbol
            """)
        )
        freshness_rows = freshness.all()
        
        return {
            "symbols": row.symbols or 0,
            "total_rows": row.total_rows or 0,
            "latest_as_of_date": row.latest_date.isoformat() if row.latest_date else None,
            "latest_knowledge_ts": row.latest_knowledge.isoformat() if row.latest_knowledge else None,
            "feature_coverage": {
                "rsi_14": row.has_rsi or 0,
                "macd_hist": row.has_macd or 0,
                "labels_fwd_ret_4w": row.has_labels or 0,
            },
            "per_symbol": [
                {
                    "symbol": r.symbol,
                    "latest_date": r.latest_date.isoformat() if r.latest_date else None,
                    "weeks": r.weeks,
                }
                for r in freshness_rows
            ],
        }
    except Exception as e:
        return {"error": str(e), "message": "Materialized view may need refresh"}


@router.get("/health/sec-coverage")
async def sec_coverage_report():
    return tag_resolver.get_coverage_report()


@router.post("/health/refresh-features")
async def refresh_features_view(db: AsyncSession = Depends(get_db)):
    try:
        bind = await db.get_bind()
        if bind.dialect.name != 'sqlite':
            await db.execute(text("REFRESH MATERIALIZED VIEW ml_features_weekly"))
            await db.commit()
            return {"success": True, "message": "Materialized view refreshed"}
        else:
            return {"success": True, "message": "SQLite does not support materialized views - skipped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health/trigger/{job_id}")
async def trigger_job(job_id: str):
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    try:
        await job.func()
        return {"success": True, "message": f"Job {job_id} executed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))