# vectorbt is optional - numpy 2.x compatibility issue
try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    vbt = None
    VECTORBT_AVAILABLE = False

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from dataclasses import dataclass
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    symbols: List[str]
    start_date: date
    end_date: date
    initial_cash: float = 100000.0
    commission: float = 0.0005  # 5 bps
    slippage: float = 0.0005  # 5 bps
    max_position_pct: float = 0.10
    freq: str = 'W'  # Weekly


@dataclass
class BacktestResult:
    config: BacktestConfig
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_return: float
    equity_curve: pd.Series
    trades: pd.DataFrame
    positions: pd.DataFrame
    metrics: Dict[str, float]


class VectorBTBacktester:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.price_data: Optional[pd.DataFrame] = None
        self.signals: Optional[pd.DataFrame] = None
    
    def load_price_data(self, ohlcv_df: pd.DataFrame):
        if ohlcv_df.empty:
            raise ValueError("Empty OHLCV data")
        
        pivot = ohlcv_df.pivot_table(
            index='time', 
            columns='symbol', 
            values='close',
            aggfunc='last'
        )
        
        pivot = pivot.resample(self.config.freq).last().ffill()
        
        self.price_data = pivot[self.config.symbols].dropna(how='all')
        logger.info(f"Loaded price data: {self.price_data.shape}")
    
    def set_signals(self, signals: pd.DataFrame):
        self.signals = signals
    
    def run_long_only(
        self,
        entry_signals: pd.DataFrame,
        exit_signals: Optional[pd.DataFrame] = None,
        size: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        if not VECTORBT_AVAILABLE:
            raise RuntimeError("vectorbt is not installed. Install with: pip install vectorbt")
        if self.price_data is None:
            raise ValueError("Price data not loaded")
        
        pf = vbt.Portfolio.from_signals(
            close=self.price_data,
            entries=entry_signals,
            exits=exit_signals,
            size=size,
            size_type='targetpercent' if size is not None else 'amount',
            init_cash=self.config.initial_cash,
            fees=self.config.commission,
            slippage=self.config.slippage,
            freq=self.config.freq,
            direction='longonly',
            max_size=self.config.max_position_pct,
        )
        
        return self._create_result(pf)
    
    def run_long_short(
        self,
        long_entries: pd.DataFrame,
        long_exits: pd.DataFrame,
        short_entries: pd.DataFrame,
        short_exits: pd.DataFrame,
        size: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        if not VECTORBT_AVAILABLE:
            raise RuntimeError("vectorbt is not installed. Install with: pip install vectorbt")
        if self.price_data is None:
            raise ValueError("Price data not loaded")
        
        pf = vbt.Portfolio.from_signals(
            close=self.price_data,
            entries=long_entries,
            exits=long_exits,
            short_entries=short_entries,
            short_exits=short_exits,
            size=size,
            size_type='targetpercent' if size is not None else 'amount',
            init_cash=self.config.initial_cash,
            fees=self.config.commission,
            slippage=self.config.slippage,
            freq=self.config.freq,
            direction='both',
            max_size=self.config.max_position_pct,
        )
        
        return self._create_result(pf)
    
    def run_from_predictions(
        self,
        predictions: pd.DataFrame,
        threshold: float = 0.0,
        position_sizing: str = 'equal',
    ) -> BacktestResult:
        if not VECTORBT_AVAILABLE:
            raise RuntimeError("vectorbt is not installed. Install with: pip install vectorbt")
        if self.price_data is None:
            raise ValueError("Price data not loaded")
        
        aligned_preds = predictions.reindex(self.price_data.index).ffill()
        aligned_preds = aligned_preds[self.config.symbols]
        
        if position_sizing == 'equal':
            n_assets = len(self.config.symbols)
            size = pd.DataFrame(1.0 / n_assets, index=aligned_preds.index, columns=self.config.symbols)
        elif position_sizing == 'vol_target':
            returns = self.price_data.pct_change()
            vol = returns.rolling(52).std() * np.sqrt(52)
            target_vol = 0.15
            size = (target_vol / (vol + 1e-8)).clip(0, self.config.max_position_pct)
        else:
            size = None
        
        entries = aligned_preds > threshold
        exits = aligned_preds <= threshold
        
        pf = vbt.Portfolio.from_signals(
            close=self.price_data,
            entries=entries,
            exits=exits,
            size=size,
            size_type='targetpercent' if size is not None else 'amount',
            init_cash=self.config.initial_cash,
            fees=self.config.commission,
            slippage=self.config.slippage,
            freq=self.config.freq,
            direction='longonly',
            max_size=self.config.max_position_pct,
        )
        
        return self._create_result(pf)
    
    def _create_result(self, pf: vbt.Portfolio) -> BacktestResult:
        stats = pf.stats()
        
        equity = pf.value()
        returns = equity.pct_change().dropna()
        
        trades = pf.trades.records_readable
        if not trades.empty:
            trades = pd.DataFrame(trades)
        
        positions = pf.get_positions()
        
        total_ret = stats.get('Total Return [%]', 0) / 100
        ann_ret = stats.get('Annualized Return [%]', 0) / 100
        sharpe = stats.get('Sharpe Ratio', 0)
        sortino = stats.get('Sortino Ratio', 0)
        max_dd = stats.get('Max Drawdown [%]', 0) / 100
        calmar = stats.get('Calmar Ratio', 0)
        
        win_rate = stats.get('Win Rate [%]', 0) / 100
        profit_factor = stats.get('Profit Factor', 0)
        total_trades = int(stats.get('Total Trades', 0))
        
        avg_trade_ret = trades['Return [%]'].mean() / 100 if not trades.empty else 0
        
        metrics = {k: float(v) if isinstance(v, (int, float, np.number)) else v 
                  for k, v in stats.to_dict().items()}
        
        return BacktestResult(
            config=self.config,
            total_return=total_ret,
            annualized_return=ann_ret,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            avg_trade_return=avg_trade_ret,
            equity_curve=equity,
            trades=trades,
            positions=positions,
            metrics=metrics,
        )
    
    def parameter_sweep(
        self,
        param_grid: Dict[str, List],
        signal_func,
        **signal_kwargs,
    ) -> pd.DataFrame:
        if not VECTORBT_AVAILABLE:
            raise RuntimeError("vectorbt is not installed. Install with: pip install vectorbt")
        results = []
        
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        
        import itertools
        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            
            try:
                signals = signal_func(**params, **signal_kwargs)
                result = self.run_long_only(
                    entry_signals=signals['entries'],
                    exit_signals=signals.get('exits'),
                    size=signals.get('size'),
                )
                
                row = {**params, **result.metrics}
                results.append(row)
            except Exception as e:
                logger.warning(f"Parameter combo {params} failed: {e}")
                continue
        
        return pd.DataFrame(results)


def create_sma_crossover_signals(
    price_data: pd.DataFrame,
    fast_period: int = 10,
    slow_period: int = 30,
) -> Dict[str, pd.DataFrame]:
    fast_sma = price_data.rolling(fast_period).mean()
    slow_sma = price_data.rolling(slow_period).mean()
    
    entries = (fast_sma > slow_sma) & (fast_sma.shift(1) <= slow_sma.shift(1))
    exits = (fast_sma < slow_sma) & (fast_sma.shift(1) >= slow_sma.shift(1))
    
    return {'entries': entries, 'exits': exits}


def create_rsi_mean_reversion_signals(
    price_data: pd.DataFrame,
    rsi_period: int = 14,
    oversold: int = 30,
    overbought: int = 70,
) -> Dict[str, pd.DataFrame]:
    delta = price_data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    entries = (rsi < oversold) & (rsi.shift(1) >= oversold)
    exits = (rsi > overbought) & (rsi.shift(1) <= overbought)
    
    return {'entries': entries, 'exits': exits}