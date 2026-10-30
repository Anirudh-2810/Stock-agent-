import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.dialects.postgresql import insert

from app.models import OHLCV, FundamentalsPointInTime
from app.core.database import get_db

logger = logging.getLogger(__name__)


class MLFeatureEngine:
    def __init__(self):
        self.feature_columns = []
    
    async def load_weekly_features(
        self, 
        db: AsyncSession, 
        symbols: List[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        query = text("""
            SELECT * FROM ml_features_weekly
            WHERE symbol = ANY(:symbols)
            AND as_of_date BETWEEN :start_date AND :end_date
            ORDER BY symbol, as_of_date
        """)
        
        result = await db.execute(query, {
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
        })
        
        rows = result.fetchall()
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=result.keys())
        return df
    
    async def load_fundamentals_latest(
        self,
        db: AsyncSession,
        symbols: List[str],
        as_of_dates: List[date],
    ) -> pd.DataFrame:
        if not as_of_dates:
            return pd.DataFrame()
        
        placeholders = ",".join([f":date_{i}" for i in range(len(as_of_dates))])
        params = {"symbols": symbols}
        for i, d in enumerate(as_of_dates):
            params[f"date_{i}"] = d
        
        query = text(f"""
            SELECT f.* FROM fundamentals_latest f
            WHERE f.symbol = ANY(:symbols)
            AND f.knowledge_timestamp <= ANY(ARRAY[{placeholders}])
            ORDER BY f.symbol, f.knowledge_timestamp DESC
        """)
        
        result = await db.execute(query, params)
        rows = result.fetchall()
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=result.keys())
        return df
    
    def create_ml_dataset(
        self,
        features_df: pd.DataFrame,
        fundamentals_df: Optional[pd.DataFrame] = None,
        target_horizon: int = 4,  # weeks
    ) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        df = features_df.copy()
        
        if fundamentals_df is not None and not fundamentals_df.empty:
            fund_cols = [c for c in fundamentals_df.columns 
                        if c not in ['symbol', 'knowledge_timestamp', 'filing_date', 'period_end', 
                                    'fiscal_year', 'fiscal_period', 'form_type', 'tags_used',
                                    'created_at', 'updated_at']]
            
            for col in fund_cols:
                if col not in df.columns:
                    df[col] = np.nan
            
            for _, fund_row in fundamentals_df.iterrows():
                symbol = fund_row['symbol']
                kts = fund_row['knowledge_timestamp']
                mask = (df['symbol'] == symbol) & (df['as_of_date'] >= kts.date() if hasattr(kts, 'date') else df['as_of_date'] >= kts)
                
                for col in fund_cols:
                    if col in fund_row and pd.notna(fund_row[col]):
                        df.loc[mask & df[col].isna(), col] = fund_row[col]
        
        target_col = f'fwd_ret_{target_horizon}w'
        if target_col not in df.columns:
            raise ValueError(f"Target column {target_col} not found")
        
        feature_cols = [c for c in df.columns 
                       if c not in ['symbol', 'as_of_date', 'knowledge_timestamp',
                                   'fwd_ret_1w', 'fwd_ret_4w', 'fwd_ret_12w']]
        
        df = df.dropna(subset=[target_col])
        
        X = df[feature_cols].fillna(method='ffill').fillna(0)
        y_reg = df[target_col]
        y_clf = (df[target_col] > 0).astype(int)
        
        self.feature_columns = list(X.columns)
        
        return X, y_reg, y_clf
    
    def add_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        if 'ret_1w' in df.columns and 'ret_4w' in df.columns:
            df['momentum_4w_1w'] = df['ret_4w'] - df['ret_1w']
        
        if 'ret_12w' in df.columns and 'ret_52w' in df.columns:
            df['momentum_52w_12w'] = df['ret_52w'] - df['ret_12w']
        
        if 'rsi_14' in df.columns:
            df['rsi_overbought'] = (df['rsi_14'] > 70).astype(int)
            df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)
        
        if 'macd_hist' in df.columns:
            df['macd_bullish'] = (df['macd_hist'] > 0).astype(int)
            df['macd_bearish'] = (df['macd_hist'] < 0).astype(int)
        
        if 'bb_pct' in df.columns:
            df['bb_squeeze'] = (df['bb_pct'] > 0.8) | (df['bb_pct'] < 0.2)
            df['bb_squeeze'] = df['bb_squeeze'].astype(int)
        
        if 'atr_14' in df.columns and 'ret_1w' in df.columns:
            df['vol_adj_ret'] = df['ret_1w'] / (df['atr_14'] + 1e-8)
        
        if 'pe_ratio' in df.columns and 'pb_ratio' in df.columns:
            df['pe_pb_ratio'] = df['pe_ratio'] / (df['pb_ratio'] + 1e-8)
        
        if 'roe' in df.columns and 'debt_to_equity' in df.columns:
            df['roe_de_ratio'] = df['roe'] / (df['debt_to_equity'] + 1e-8)
        
        return df


ml_feature_engine = MLFeatureEngine()