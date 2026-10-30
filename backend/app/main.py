from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import sys
import traceback

from app.core.config import settings
from app.core.database import init_db, engine
from app.core.redis import get_redis, close_redis
from app.api.v1 import trading, websocket, data_health, backtest, signals, analysis
from app.services.alpaca_ws import alpaca_ws
from app.services.execution_guards import execution_guards
from app.tasks.scheduler import init_scheduler, start_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    
    try:
        await init_db()
        logger.info("Database initialized")
        
        redis = await get_redis()
        logger.info("Redis connected")
        
        await execution_guards.initialize()
        logger.info("Execution guards initialized")
        
        await alpaca_ws.start()
        logger.info("Alpaca WebSocket started")
        
        # MLflow optional - only initialize if available
        try:
            import mlflow
            mlflow.set_tracking_uri(getattr(settings, 'mlflow_tracking_uri', 'file:./mlruns'))
            mlflow.set_experiment("stock_agent")
            logger.info("MLflow initialized")
        except ImportError:
            logger.warning("MLflow not installed - experiment tracking disabled")
        
        init_scheduler()
        if settings.enable_scheduler:
            start_scheduler()
            logger.info("Scheduler started (ENABLE_SCHEDULER=true)")
        else:
            logger.info("Scheduler initialized (not started - set ENABLE_SCHEDULER=true)")
        
        logger.info("Startup complete, yielding control")
        yield
        
        logger.info("Shutting down...")
        shutdown_scheduler()
        await alpaca_ws.stop()
        await close_redis()
        await engine.dispose()
        logger.info("Shutdown complete")
    except Exception as e:
        logger.error(f"Lifespan error: {e}")
        logger.error(traceback.format_exc())
        raise


app = FastAPI(
    title="Stock Agent API",
    description="Algorithmic trading engine with paper trading",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trading.router)
app.include_router(websocket.router)
app.include_router(data_health.router)
app.include_router(backtest.router)
app.include_router(signals.router)
app.include_router(analysis.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.environment}


@app.get("/")
async def root():
    return {"message": "Stock Agent API", "docs": "/docs"}