import { useEffect, useMemo, useState } from 'react';
import { signalsApi } from '../services/api';
import { Card, Spinner, ErrorState, Badge } from '../components/ui';
import type { SignalScanResponse, SymbolSignal } from '../types';

const UNIVERSE = 'AAPL,NVDA,SPY,QQQ,MSFT,GOOGL,AMZN,META,TSLA,JPM';
type ActionFilter = 'ALL' | 'BUY' | 'SELL' | 'HOLD';

const COMPONENT_LABELS: Record<string, string> = {
  sma_cross: 'SMA Cross',
  rsi: 'RSI',
  macd: 'MACD',
  momentum: 'Momentum',
  volume: 'Volume',
  trend: 'Trend',
};

export function Signals() {
  const [data, setData] = useState<SignalScanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<ActionFilter>('ALL');
  const [days, setDays] = useState(250);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await signalsApi.scan(UNIVERSE, days);
        setData(res);
      } catch (e) {
        setError('Failed to scan signals. Is the backend running?');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [days]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === 'ALL') return data.signals;
    return data.signals.filter(s => s.action === filter);
  }, [data, filter]);

  const scoreColor = (score: number) => (score >= 0.4 ? 'text-primary-600' : score <= -0.4 ? 'text-danger-600' : 'text-gray-500');

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Signals</h1>
          <p className="text-gray-500">Multi-factor technical consensus across the universe</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-500">
            Lookback
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              className="ml-2 px-3 py-1.5 border border-gray-300 rounded text-sm bg-white"
            >
              {[90, 250, 500].map(d => <option key={d} value={d}>{d}d</option>)}
            </select>
          </label>
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            {(['ALL', 'BUY', 'SELL', 'HOLD'] as ActionFilter[]).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                  filter === f ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {f === 'ALL' ? `All (${data?.signals.length ?? 0})` : `${f} (${data ? data.counts[f.toLowerCase() as 'buy' | 'sell' | 'hold'] : 0})`}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && <ErrorState message={error} />}
      {loading && <Spinner />}

      {!loading && data && (
        <div className="space-y-6">
          {data.model_blend && (
            <div className="bg-blue-50 border border-blue-100 text-blue-700 text-xs rounded-lg px-4 py-2">
              ML model predictions blended into these signals
            </div>
          )}

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
                    <th className="pb-3 pr-4">Symbol</th>
                    <th className="pb-3 pr-4">Action</th>
                    <th className="pb-3 pr-4">Score</th>
                    <th className="pb-3 pr-4">Tech</th>
                    {data.model_blend && <th className="pb-3 pr-4">ML</th>}
                    <th className="pb-3 pr-4">Confidence</th>
                    <th className="pb-3">Components</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(s => (
                    <SignalRow key={s.symbol} signal={s} showMl={data.model_blend} scoreColor={scoreColor} />
                  ))}
                  {filtered.length === 0 && (
                    <tr><td colSpan={7} className="py-8 text-center text-gray-400">No signals in this bucket</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function SignalRow({
  signal, showMl, scoreColor,
}: {
  signal: SymbolSignal;
  showMl: boolean;
  scoreColor: (score: number) => string;
}) {
  return (
    <tr className="border-b border-gray-50 hover:bg-gray-50">
      <td className="py-3 pr-4 font-semibold text-gray-800">{signal.symbol}</td>
      <td className="py-3 pr-4">
        <Badge tone={signal.action.toLowerCase() as 'buy' | 'sell' | 'hold'}>{signal.action}</Badge>
      </td>
      <td className={`py-3 pr-4 font-semibold ${scoreColor(signal.score)}`}>{signal.score.toFixed(2)}</td>
      <td className="py-3 pr-4 text-gray-500">{signal.technical_score.toFixed(2)}</td>
      {showMl && (
        <td className="py-3 pr-4 text-gray-500">
          {signal.ml_score != null ? signal.ml_score.toFixed(2) : '—'}
        </td>
      )}
      <td className="py-3 pr-4 text-gray-500">{(signal.confidence * 100).toFixed(0)}%</td>
      <td className="py-3">
        <div className="flex gap-1.5 flex-wrap">
          {Object.entries(signal.components).map(([key, value]) => (
            <span
              key={key}
              title={`${COMPONENT_LABELS[key] ?? key}: ${value.toFixed(2)}`}
              className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
                value > 0.2 ? 'bg-green-50 text-green-700' : value < -0.2 ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-500'
              }`}
            >
              {value.toFixed(1)}
            </span>
          ))}
        </div>
      </td>
    </tr>
  );
}