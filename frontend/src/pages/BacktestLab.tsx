import { useEffect, useState } from 'react';
import { backtestApi } from '../services/api';
import { Card, Spinner, ErrorState, StatCard } from '../components/ui';
import type { BacktestResult, BacktestModel } from '../types';

const STRATEGIES = ['sma_crossover', 'rsi_mean_reversion', 'ml_predictions'];

export function BacktestLab() {
  const [symbols, setSymbols] = useState('AAPL,MSFT');
  const [startDate, setStartDate] = useState('2023-01-01');
  const [endDate, setEndDate] = useState('2024-12-31');
  const [strategy, setStrategy] = useState('sma_crossover');
  const [initialCash, setInitialCash] = useState(100000);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [models, setModels] = useState<BacktestModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    backtestApi.models()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  const run = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        symbols,
        start_date: startDate,
        end_date: endDate,
        strategy,
        initial_cash: initialCash,
      };
      const res = await backtestApi.run(params);
      setResult(res);
    } catch (e) {
      setError('Backtest failed. Check parameters and data availability.');
    } finally {
      setLoading(false);
    }
  };

  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">Backtest Lab</h1>
        <p className="text-gray-500">VectorBT-powered strategy testing against historical data</p>
      </header>

      {error && <ErrorState message={error} />}

      <Card title="Backtest Configuration">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Field label="Symbols" hint="comma separated">
            <input value={symbols} onChange={e => setSymbols(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Strategy">
            <select value={strategy} onChange={e => setStrategy(e.target.value)} className={inputCls}>
              {STRATEGIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Start">
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className={inputCls} />
          </Field>
          <Field label="End">
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Initial Cash">
            <input type="number" value={initialCash} onChange={e => setInitialCash(Number(e.target.value))} className={inputCls} />
          </Field>
        </div>
        <div className="mt-4">
          <button
            onClick={run}
            disabled={loading}
            className="px-5 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {loading ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
      </Card>

      {loading && <Spinner />}

      {result && !loading && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Return" value={pct(result.total_return)} tone={result.total_return >= 0 ? 'positive' : 'negative'} />
            <StatCard label="Annualized" value={pct(result.annualized_return)} tone={result.annualized_return >= 0 ? 'positive' : 'negative'} />
            <StatCard label="Sharpe" value={result.sharpe_ratio.toFixed(2)} />
            <StatCard label="Max Drawdown" value={pct(result.max_drawdown)} tone="negative" />
            <StatCard label="Sortino" value={result.sortino_ratio.toFixed(2)} />
            <StatCard label="Win Rate" value={pct(result.win_rate)} />
            <StatCard label="Profit Factor" value={result.profit_factor.toFixed(2)} />
            <StatCard label="Total Trades" value={result.total_trades} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card title="Equity Curve">
              <EquityCurve curve={result.equity_curve} />
            </Card>
            <Card title="Trades">
              <div className="overflow-x-auto max-h-80">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-400 uppercase border-b border-gray-100">
                      <th className="py-2 pr-3">Symbol</th>
                      <th className="py-2 pr-3">Side</th>
                      <th className="py-2 pr-3">Entry</th>
                      <th className="py-2 pr-3">Exit</th>
                      <th className="py-2 pr-3">Return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-1.5 pr-3 font-medium">{String(t.Symbol ?? t.symbol ?? '—')}</td>
                        <td className="py-1.5 pr-3">{String(t.Side ?? t.side ?? '—')}</td>
                        <td className="py-1.5 pr-3">{String(t['Entry Price'] ?? t.entry_price ?? '—')}</td>
                        <td className="py-1.5 pr-3">{String(t['Exit Price'] ?? t.exit_price ?? '—')}</td>
                        <td className="py-1.5 pr-3">{t['Return [%]'] != null ? `${Number(t['Return [%]']).toFixed(2)}%` : '—'}</td>
                      </tr>
                    ))}
                    {result.trades.length === 0 && (
                      <tr><td colSpan={5} className="py-6 text-center text-gray-400">No trades recorded</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </div>
      )}

      <Card title="Registered Models">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Version</th>
                <th className="py-2 pr-4">Task</th>
                <th className="py-2 pr-4">Registered</th>
                <th className="py-2">MLflow Run</th>
              </tr>
            </thead>
            <tbody>
              {models.map(m => (
                <tr key={`${m.name}:${m.version}`} className="border-b border-gray-50">
                  <td className="py-2 pr-4 font-medium">{m.name}</td>
                  <td className="py-2 pr-4">{m.version}</td>
                  <td className="py-2 pr-4">{String(m.config?.task ?? '—')}</td>
                  <td className="py-2 pr-4 text-gray-500">{m.registered_at?.slice(0, 19).replace('T', ' ')}</td>
                  <td className="py-2 text-gray-500">{String(m.mlflow_run_id ?? '—')}</td>
                </tr>
              ))}
              {models.length === 0 && (
                <tr><td colSpan={5} className="py-6 text-center text-gray-400">No trained models registered yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

const inputCls = 'w-full px-3 py-1.5 border border-gray-300 rounded text-sm bg-white';

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}{hint && <span className="text-gray-400 ml-1">({hint})</span>}</label>
      {children}
    </div>
  );
}

function EquityCurve({ curve }: { curve: Record<string, number> }) {
  const points = Object.entries(curve).map(([t, v]) => ({ t, v }));
  if (points.length < 2) {
    return <div className="h-48 flex items-center justify-center text-gray-400 text-xs">No equity data</div>;
  }
  const values = points.map(p => p.v);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * 100;
    const y = 100 - ((p.v - min) / range) * 100;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const up = values[values.length - 1] >= values[0];

  return (
    <div className="h-48">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
        <polyline points={coords} fill="none" stroke={up ? '#22c55e' : '#ef4444'} strokeWidth="1.5" />
      </svg>
    </div>
  );
}