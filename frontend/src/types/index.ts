export interface OrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop' | 'stop_limit';
  time_in_force: 'day' | 'gtc' | 'opg' | 'cls' | 'ioc' | 'fok';
  qty: number;
  limit_price?: number;
  stop_price?: number;
  client_order_id?: string;
}

export interface OrderResponse {
  id: string;
  alpaca_order_id?: string;
  client_order_id?: string;
  symbol: string;
  side: string;
  type: string;
  time_in_force: string;
  qty: number;
  limit_price?: number;
  stop_price?: number;
  filled_qty: number;
  filled_avg_price?: number;
  status: string;
  submitted_at?: string;
  filled_at?: string;
  canceled_at?: string;
  created_at: string;
  updated_at: string;
}

export interface PositionResponse {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  avg_entry_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  current_price: number;
  lastday_price: number;
  change_today: number;
  created_at: string;
  updated_at: string;
}

export interface AccountResponse {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  daily_pl: number;
  daily_plpc: number;
  positions_count: number;
}

export interface FillResponse {
  id: string;
  order_id: string;
  alpaca_trade_id: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  timestamp: string;
  created_at: string;
}

export interface GuardStatus {
  guard_type: string;
  is_active: boolean;
  config: Record<string, any>;
  triggered_at?: string;
  trigger_count: number;
}

export interface GuardUpdate {
  is_active: boolean;
}

export interface KillSwitchRequest {
  activate: boolean;
}

export interface QuoteData {
  symbol: string;
  bid_price: number;
  bid_size: number;
  ask_price: number;
  ask_size: number;
  timestamp: string;
}

export interface TradeData {
  symbol: string;
  price: number;
  size: number;
  timestamp: string;
  exchange: string;
}

export interface WSMessage {
  type: 'quote' | 'trade' | 'order_update' | 'position_update' | 'account_update';
  data: any;
}

// ===== Signals =====
export interface SignalComponent {
  sma_cross: number;
  rsi: number;
  macd: number;
  momentum: number;
  volume: number;
  trend: number;
}

export interface SymbolSignal {
  symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  score: number;
  technical_score: number;
  ml_score?: number | null;
  confidence: number;
  components: SignalComponent;
  error?: string;
}

export interface SignalScanResponse {
  generated_at: string;
  counts: { buy: number; sell: number; hold: number };
  model_blend: boolean;
  signals: SymbolSignal[];
}

export interface SignalQuote {
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number | null;
  change: number;
  change_pct: number;
  as_of: string;
}

export interface SymbolSignalDetail {
  symbol: string;
  signal: SymbolSignal;
  quote: SignalQuote;
  indicators: Record<string, number>;
}

export interface PortfolioSignalSummary {
  total: number;
  strong_buys: number;
  buys: number;
  sells: number;
  avg_score: number;
  top_picks: SymbolSignal[];
  worst_picks: SymbolSignal[];
}

// ===== Analysis =====
export interface IndexPerformance {
  symbol: string;
  close: number;
  change_pct: number;
  window_start: string;
  window_end: string;
  bars: number;
}

export interface MarketOverview {
  as_of: string;
  window_days: number;
  indexes: IndexPerformance[];
  best: IndexPerformance[];
  worst: IndexPerformance[];
}

export interface AnalysisSummary {
  close: number;
  change_pct: number;
  day_range_high: number;
  day_range_low: number;
  period_return_pct: number;
  volatility_annual: number;
  avg_volume: number;
}

export interface Fundamentals {
  filing_date: string | null;
  period_end: string | null;
  revenue: number | null;
  net_income: number | null;
  eps_basic: number | null;
  total_assets: number | null;
  stockholders_equity: number | null;
  shares_outstanding: number | null;
  pe_ratio: number | null;
  tags_used?: Record<string, string> | null;
}

export interface SymbolAnalysis {
  symbol: string;
  summary: AnalysisSummary;
  indicators: Record<string, number>;
  fundamentals: Fundamentals | null;
  history: { time: string; open: number; high: number; low: number; close: number; volume?: number | null }[];
  bars: number;
}

export interface ComparePoint {
  time: string;
  value: number;
}

export interface CompareResponse {
  symbols: string[];
  baseline: number;
  series: Record<string, ComparePoint[]>;
}

// ===== Data Health =====
export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
  trigger: string;
}

export interface DataHealthSummary {
  timestamp: string;
  ohlcv: {
    symbols_with_data: number;
    total_bars_7d: number;
    latest_bar: string | null;
    latest_ingestion: string | null;
    ingestion_lag_hours: number | null;
  };
  corporate_actions: {
    symbols_with_actions: number;
    total_actions_7d: number;
    latest_ex_date: string | null;
  };
  scheduler: {
    running: boolean;
    jobs: SchedulerJob[];
  };
}

export interface OHLCVHealth {
  symbol: string;
  period_days: number;
  bars_found: number;
  first_bar: string | null;
  last_bar: string | null;
  latest_ingestion: string | null;
  avg_volume: number;
  missing_trading_days: number;
  data_complete: boolean;
}

export interface FundamentalsHealth {
  total_symbols: number;
  total_filings: number;
  latest_filing: string | null;
  latest_knowledge_ts: string | null;
  coverage: {
    symbol: string;
    filings: number;
    latest_filing: string | null;
    metrics_present: { net_income: number; revenue: number; total_assets: number; shares_outstanding: number };
  }[];
}

export interface FeaturesHealth {
  symbols: number;
  total_rows: number;
  latest_as_of_date: string | null;
  latest_knowledge_ts: string | null;
  feature_coverage: { rsi_14: number; macd_hist: number; labels_fwd_ret_4w: number };
  per_symbol: { symbol: string; latest_date: string | null; weeks: number }[];
}

export type SecurityCoverage = Record<string, { available: string[]; missing: string[]; coverage_pct: number }>;

// ===== Backtest =====
export interface BacktestRunRequest {
  symbols: string;
  start_date: string;
  end_date: string;
  strategy: string;
  initial_cash?: number;
  commission?: number;
  slippage?: number;
  model_name?: string;
  model_version?: string;
  threshold?: number;
  position_sizing?: string;
  fast?: number;
  slow?: number;
  rsi_period?: number;
  oversold?: number;
  overbought?: number;
}

export interface BacktestResult {
  config: Record<string, unknown>;
  metrics: Record<string, number>;
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  calmar_ratio: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  avg_trade_return: number;
  equity_curve: Record<string, number>;
  trades: Record<string, unknown>[];
}

export interface BacktestModel {
  name: string;
  version: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  registered_at: string;
  model_path: string;
  mlflow_run_id?: string | null;
}