from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.dialects.postgresql import insert
import sqlalchemy as sa

from app.models import OHLCV, CorporateAction, Ticker, FundamentalsPointInTime
from app.services.yfinance_ingester import yfinance_ingester
from app.services.sec_parser import sec_parser, ParsedFiling
from app.services.feature_engine import feature_store
from app.core.database import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "JPM", "WMT",
    "UNH", "V", "XOM", "MA", "PG", "JNJ", "HD", "CVX", "LLY", "MRK",
    "ABBV", "PEP", "KO", "COST", "TMO", "ACN", "ABT", "BAC", "DHR", "CRM",
    "ADBE", "NFLX", "NKE", "TXN", "AMD", "INTC", "QCOM", "AVGO", "CSCO", "ORCL",
    "IBM", "GE", "MMM", "CAT", "HON", "UPS", "RTX", "LMT", "BA", "DE",
    "SPY", "QQQ", "IWM", "EFA", "EEM", "GLD", "TLT", "HYG", "LQD", "VCIT",
]


class DataIngestionService:
    def __init__(self, universe: List[str] = None):
        self.universe = universe or DEFAULT_UNIVERSE
        self.sec_parser = sec_parser
        self.yf_ingester = yfinance_ingester
    
    async def run_daily_ohlcv(self, days_back: int = 5) -> Dict:
        logger.info(f"Running daily OHLCV ingestion for {len(self.universe)} symbols")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        ohlcv_results = await self.yf_ingester.fetch_ohlcv(
            self.universe,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )
        
        ca_results = await self.yf_ingester.fetch_corporate_actions(self.universe)
        
        total_bars = 0
        total_actions = 0
        
        async for db in get_db():
            for symbol, bars in ohlcv_results.items():
                if bars:
                    count = await self.yf_ingester.upsert_ohlcv(db, bars)
                    total_bars += count
            
            for symbol, actions in ca_results.items():
                if actions:
                    count = await self.yf_ingester.upsert_corporate_actions(db, actions)
                    total_actions += count
        
        logger.info(f"Daily OHLCV complete: {total_bars} bars, {total_actions} actions")
        return {"bars": total_bars, "actions": total_actions}
    
    async def run_sec_ingestion(self, max_filings_per_ticker: int = 2) -> Dict:
        logger.info(f"Running SEC ingestion for {len(self.universe)} symbols")
        
        total_filings = 0
        total_metrics = 0
        errors = []
        
        async for db in get_db():
            for symbol in self.universe:
                try:
                    cik = self.sec_parser.get_cik(symbol)
                    if not cik:
                        errors.append(f"{symbol}: No CIK found")
                        continue
                    
                    filings = self.sec_parser.get_company_filings(cik, ["10-K", "10-Q"])
                    if not filings:
                        errors.append(f"{symbol}: No filings found")
                        continue
                    
                    for filing in filings[:max_filings_per_ticker]:
                        parsed = self.sec_parser.parse_filing(symbol, filing)
                        if not parsed:
                            continue
                        
                        await self._upsert_fundamentals(db, parsed)
                        total_filings += 1
                        total_metrics += sum(1 for v in parsed.metrics.values() if v[0] is not None)
                        
                except Exception as e:
                    logger.error(f"SEC ingestion failed for {symbol}: {e}")
                    errors.append(f"{symbol}: {str(e)}")
        
        logger.info(f"SEC ingestion complete: {total_filings} filings, {total_metrics} metrics")
        return {
            "filings": total_filings,
            "metrics": total_metrics,
            "errors": errors,
        }
    
    async def _upsert_fundamentals(self, db: AsyncSession, parsed: ParsedFiling) -> None:
        filing = parsed.filing_info
        metrics = parsed.metrics
        
        tags_used = {k: v[1] for k, v in metrics.items() if v[1] is not None}
        
        stmt = insert(
            FundamentalsPointInTime
        ).values(
            symbol=parsed.ticker,
            period_end=filing.report_date,
            filing_date=filing.filing_date,
            knowledge_timestamp=parsed.knowledge_timestamp,
            form_type=filing.form_type,
            fiscal_year=filing.fiscal_year,
            fiscal_period=filing.fiscal_period,
            net_income=metrics.get("net_income", (None, None))[0],
            revenue=metrics.get("revenue", (None, None))[0],
            total_assets=metrics.get("total_assets", (None, None))[0],
            total_liabilities=metrics.get("total_liabilities", (None, None))[0],
            stockholders_equity=metrics.get("stockholders_equity", (None, None))[0],
            shares_outstanding=metrics.get("shares_outstanding", (None, None))[0],
            eps_basic=metrics.get("eps_basic", (None, None))[0],
            operating_income=metrics.get("operating_income", (None, None))[0],
            cash_equivalents=metrics.get("cash_equivalents", (None, None))[0],
            gross_profit=metrics.get("gross_profit", (None, None))[0],
            research_development=metrics.get("research_development", (None, None))[0],
            selling_general_admin=metrics.get("selling_general_admin", (None, None))[0],
            depreciation_amortization=metrics.get("depreciation_amortization", (None, None))[0],
            interest_expense=metrics.get("interest_expense", (None, None))[0],
            income_tax_expense=metrics.get("income_tax_expense", (None, None))[0],
            capital_expenditures=metrics.get("capital_expenditures", (None, None))[0],
            free_cash_flow=metrics.get("free_cash_flow", (None, None))[0],
            dividends_per_share=metrics.get("dividends_per_share", (None, None))[0],
            book_value_per_share=metrics.get("book_value_per_share", (None, None))[0],
            tags_used=tags_used,
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "period_end", "filing_date"],
            set_={
                "knowledge_timestamp": stmt.excluded.knowledge_timestamp,
                "form_type": stmt.excluded.form_type,
                "fiscal_year": stmt.excluded.fiscal_year,
                "fiscal_period": stmt.excluded.fiscal_period,
                "net_income": stmt.excluded.net_income,
                "revenue": stmt.excluded.revenue,
                "total_assets": stmt.excluded.total_assets,
                "total_liabilities": stmt.excluded.total_liabilities,
                "stockholders_equity": stmt.excluded.stockholders_equity,
                "shares_outstanding": stmt.excluded.shares_outstanding,
                "eps_basic": stmt.excluded.eps_basic,
                "operating_income": stmt.excluded.operating_income,
                "cash_equivalents": stmt.excluded.cash_equivalents,
                "gross_profit": stmt.excluded.gross_profit,
                "research_development": stmt.excluded.research_development,
                "selling_general_admin": stmt.excluded.selling_general_admin,
                "depreciation_amortization": stmt.excluded.depreciation_amortization,
                "interest_expense": stmt.excluded.interest_expense,
                "income_tax_expense": stmt.excluded.income_tax_expense,
                "capital_expenditures": stmt.excluded.capital_expenditures,
                "free_cash_flow": stmt.excluded.free_cash_flow,
                "dividends_per_share": stmt.excluded.dividends_per_share,
                "book_value_per_share": stmt.excluded.book_value_per_share,
                "tags_used": stmt.excluded.tags_used,
                "updated_at": sa.func.now(),
            },
        )
        
        await db.execute(stmt)
        await db.commit()
    
    async def run_feature_computation(self) -> Dict:
        logger.info("Running feature computation for universe")
        
        results = {}
        
        async for db in get_db():
            feature_data = await feature_store.compute_for_universe(db, self.universe)
            
            for symbol, df in feature_data.items():
                if not df.empty:
                    results[symbol] = len(df)
            
            # Refresh materialized view (PostgreSQL only - SQLite doesn't support materialized views)
            bind = db.get_bind()
            if bind.dialect.name != 'sqlite':
                await db.execute(text("REFRESH MATERIALIZED VIEW ml_features_weekly"))
                await db.commit()
        
        logger.info(f"Feature computation complete for {len(results)} symbols")
        return {"symbols_computed": len(results), "rows": results}
    
    async def run_full_pipeline(self) -> Dict:
        logger.info("Starting full data pipeline")
        
        results = {}
        
        results["ohlcv"] = await self.run_daily_ohlcv()
        results["sec"] = await self.run_sec_ingestion()
        results["features"] = await self.run_feature_computation()
        
        logger.info("Full pipeline complete")
        return results


data_ingestion = DataIngestionService()