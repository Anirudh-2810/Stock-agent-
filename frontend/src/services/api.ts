import axios from 'axios';
import type {
  OrderRequest, OrderResponse, PositionResponse, AccountResponse, GuardStatus, GuardUpdate, QuoteData,
  SignalScanResponse, SymbolSignalDetail, PortfolioSignalSummary,
  MarketOverview, SymbolAnalysis, CompareResponse,
  DataHealthSummary, OHLCVHealth, FundamentalsHealth, FeaturesHealth, SecurityCoverage,
  BacktestRunRequest, BacktestResult, BacktestModel,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || '';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  },
  timeout: 10000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 403) {
      console.error('API Key invalid or missing');
    }
    // Throw on any error status so callers can catch it
    return Promise.reject(error);
  }
);

export const accountApi = {
  get: () => api.get<AccountResponse>('/account').then(r => r.data),
};

export const positionsApi = {
  get: () => api.get<PositionResponse[]>('/positions').then(r => r.data),
  close: (symbol: string) => api.post(`/positions/${symbol}/close`).then(r => r.data),
  closeAll: () => api.post('/positions/close-all').then(r => r.data),
};

export const ordersApi = {
  get: (status?: string, limit = 100) => api.get<OrderResponse[]>('/orders', { params: { status, limit } }).then(r => r.data),
  place: (order: OrderRequest) => api.post<OrderResponse>('/orders', order).then(r => r.data),
  cancel: (orderId: string) => api.post(`/orders/${orderId}/cancel`).then(r => r.data),
};

export const guardsApi = {
  get: () => api.get<Record<string, GuardStatus>>('/guards').then(r => r.data),
  update: (guardType: string, update: GuardUpdate) => api.post(`/guards/${guardType}`, update).then(r => r.data),
  killSwitch: (activate: boolean) => api.post('/kill-switch', { activate }).then(r => r.data),
};

export const quotesApi = {
  get: (symbols: string) => api.get<QuoteData[]>('/quotes', { params: { symbols } }).then(r => r.data),
};

export const signalsApi = {
  scan: (symbols: string, days = 250, modelName?: string) =>
    api.get<SignalScanResponse>('/signals/scan', { params: { symbols, days, model_name: modelName } }).then(r => r.data),
  getSymbol: (symbol: string, days = 250, modelName?: string) =>
    api.get<SymbolSignalDetail>(`/signals/${symbol}`, { params: { days, model_name: modelName } }).then(r => r.data),
  summary: (symbols: string, modelName?: string) =>
    api.get<PortfolioSignalSummary>('/signals/portfolio/summary', { params: { symbols, model_name: modelName } }).then(r => r.data),
};

export const analysisApi = {
  overview: (symbols: string, days = 30) =>
    api.get<MarketOverview>('/analysis/overview', { params: { symbols, days } }).then(r => r.data),
  symbol: (symbol: string, days = 250) =>
    api.get<SymbolAnalysis>(`/analysis/symbol/${symbol}`, { params: { days } }).then(r => r.data),
  compare: (symbols: string, days = 90) =>
    api.get<CompareResponse>('/analysis/compare', { params: { symbols, days } }).then(r => r.data),
};

export const dataApi = {
  summary: () => api.get<DataHealthSummary>('/data/health/summary').then(r => r.data),
  ohlcv: (symbol: string, days = 30) =>
    api.get<OHLCVHealth>(`/data/health/ohlcv/${symbol}`, { params: { days } }).then(r => r.data),
  fundamentals: () => api.get<FundamentalsHealth>('/data/health/fundamentals').then(r => r.data),
  features: () => api.get<FeaturesHealth>('/data/health/features').then(r => r.data),
  secCoverage: () => api.get<SecurityCoverage>('/data/health/sec-coverage').then(r => r.data),
  refreshFeatures: () => api.post('/data/health/refresh-features').then(r => r.data),
  triggerJob: (jobId: string) => api.post(`/data/health/trigger/${jobId}`).then(r => r.data),
};

export const backtestApi = {
  run: (params: BacktestRunRequest) => api.post<BacktestResult>('/backtest/run', null, { params }).then(r => r.data),
  sweep: (params: Record<string, unknown>) => api.post('/backtest/parameter-sweep', params.grid, { params: params.extra }).then(r => r.data),
  models: () => api.get<BacktestModel[]>('/backtest/models').then(r => r.data),
  getModel: (name: string, version = 'production') =>
    api.get<BacktestModel>(`/backtest/models/${name}/${version}`).then(r => r.data),
  promote: (name: string, version: string) =>
    api.post(`/backtest/models/${name}/${version}/promote`).then(r => r.data),
  predict: (modelName: string, symbols: string, asOfDate: string, returnProba = false) =>
    api.post<Record<string, unknown>>('/backtest/predict', null, {
      params: { model_name: modelName, symbols, as_of_date: asOfDate, return_proba: returnProba },
    }).then(r => r.data),
  train: (params: Record<string, unknown>) => api.post('/backtest/train', null, { params }).then(r => r.data),
  walkForward: (params: Record<string, unknown>) => api.post('/backtest/walk-forward', null, { params }).then(r => r.data),
  retrainWeekly: (symbols: string) =>
    api.post('/backtest/retrain-weekly', null, { params: { symbols } }).then(r => r.data),
};

export default api;