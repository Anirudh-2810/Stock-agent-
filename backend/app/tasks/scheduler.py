from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import logging
from app.services.data_ingestion import data_ingestion
from app.services.execution_guards import execution_guards
from app.services.alpaca_ws import alpaca_ws
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def daily_ohlcv_job():
    try:
        logger.info("Running scheduled daily OHLCV ingestion")
        result = await data_ingestion.run_daily_ohlcv(days_back=5)
        logger.info(f"Daily OHLCV job result: {result}")
    except Exception as e:
        logger.error(f"Daily OHLCV job failed: {e}")


async def daily_sec_job():
    try:
        logger.info("Running scheduled SEC ingestion")
        result = await data_ingestion.run_sec_ingestion(max_filings_per_ticker=1)
        logger.info(f"SEC job result: {result}")
    except Exception as e:
        logger.error(f"SEC job failed: {e}")


async def daily_features_job():
    try:
        logger.info("Running scheduled feature computation")
        result = await data_ingestion.run_feature_computation()
        logger.info(f"Feature job result: {result}")
    except Exception as e:
        logger.error(f"Feature job failed: {e}")


async def full_pipeline_job():
    try:
        logger.info("Running scheduled full pipeline")
        result = await data_ingestion.run_full_pipeline()
        logger.info(f"Full pipeline result: {result}")
    except Exception as e:
        logger.error(f"Full pipeline job failed: {e}")


async def equity_snapshot_job():
    try:
        from app.services.alpaca_rest import alpaca_rest
        account = await alpaca_rest.get_account()
        await execution_guards.record_equity(float(account.equity))
        logger.info(f"Equity snapshot recorded: {account.equity}")
    except Exception as e:
        logger.error(f"Equity snapshot job failed: {e}")


async def ws_health_check_job():
    try:
        redis = await get_redis()
        await redis.set("health:ws:last_check", str(datetime.utcnow()), ex=300)
        
        if not alpaca_ws._running:
            logger.warning("Alpaca WS not running, attempting restart")
            await alpaca_ws.start()
        else:
            logger.debug("Alpaca WS health check OK")
    except Exception as e:
        logger.error(f"WS health check failed: {e}")


async def guard_health_check_job():
    try:
        status = await execution_guards.get_status()
        redis = await get_redis()
        await redis.set("health:guards:status", str(status), ex=300)
        
        for guard_type, guard_data in status.items():
            if not guard_data["enabled"]:
                logger.warning(f"Guard disabled: {guard_type}")
    except Exception as e:
        logger.error(f"Guard health check failed: {e}")


def init_scheduler():
    scheduler.add_job(
        daily_ohlcv_job,
        CronTrigger(hour=6, minute=30, timezone="America/New_York"),
        id="daily_ohlcv",
        name="Daily OHLCV Ingestion",
        max_instances=1,
        coalesce=True,
    )
    
    scheduler.add_job(
        daily_sec_job,
        CronTrigger(hour=7, minute=0, timezone="America/New_York"),
        id="daily_sec",
        name="Daily SEC Filings Ingestion",
        max_instances=1,
        coalesce=True,
    )
    
    scheduler.add_job(
        daily_features_job,
        CronTrigger(hour=8, minute=0, timezone="America/New_York"),
        id="daily_features",
        name="Daily Feature Computation",
        max_instances=1,
        coalesce=True,
    )
    
    scheduler.add_job(
        equity_snapshot_job,
        IntervalTrigger(minutes=5),
        id="equity_snapshot",
        name="Equity Snapshot for Drawdown Guard",
        max_instances=1,
    )
    
    scheduler.add_job(
        ws_health_check_job,
        IntervalTrigger(minutes=2),
        id="ws_health_check",
        name="WebSocket Health Check",
        max_instances=1,
    )
    
    scheduler.add_job(
        guard_health_check_job,
        IntervalTrigger(minutes=1),
        id="guard_health_check",
        name="Execution Guards Health Check",
        max_instances=1,
    )
    
    logger.info("Scheduler initialized with all jobs")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")