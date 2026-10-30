import { useEffect, useState } from 'react';
import { analysisApi } from '../services/api';
import { Card, Spinner, ErrorState, StatCard } from '../components/ui';
import type { SymbolAnalysis, CompareResponse } from '../types';

const UNIVERSE = ['AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM', 'SPY', 'QQQ'];

export function Analysis() {
  const [symbol, setSymbol] = useState('AAPL');
  const [days, setDays] = useState(250);
  const [data, setData] = useState<SymbolAnalysis | null>(null);
  const [compare, setCompare] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const [detail, cmp] = await Promise.all([
          analysisApi.symbol(symbol, days),
          analysisApi.compare(symbol + ',SPY,QQQ', Math.min(days, 250)),
        ]);
        setData(detail);
        setCompare(cmp);
      } catch (e) {
        setError(`Failed to load analysis for ${symbol}`);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [symbol, days]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analysis</h1>
          <p className="text-gray-500">Deep dive: price action, technicals, and fundamentals</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white"
          >
            {UNIVERSE.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white"
          >
            {[90, 250, 500].map(d => <option key={d} value={d}>{d}d</option>)}
          </select>
        </div>
      </header>

      {error && <ErrorState message={error} />}
      {loading && <Spinner />}

      {!loading && data && (
        <div className="space-y-6">
          {/* Summary stats */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <StatCard label="Close" value={data.summary.close.toFixed(2)} sublabel={`${data.summary.change_pct >= 0 ? '+' : ''}${data.summary.change_pct.toFixed(2)}% today`}
              tone={data.summary.change_pct >= 0 ? 'positive' : 'negative'} />
            <StatCard label="Period Return" value={`${data.summary.period_return_pct.toFixed(2)}%`} sublabel={`${days}d window`}
              tone={data.summary.period_return_pct >= 0 ? 'positive' : 'negative'} />
            <StatCard label="Annualized Vol" value={`${data.summary.volatility_annual.toFixed(1)}%`} />
            <StatCard label="Day Range" value={`${data.summary.day_range_low.toFixed(2)}–${data.summary.day_range_high.toFixed(2)}`} />
            <StatCard label="Avg Volume" value={data.summary.avg_volume.toLocaleString()} />
          </div>

          {/* Price + fundamentals */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <Card title="Price Chart (mock rendering)">
                <div className="text-xs text-gray-400 mb-3">
                  Connect a live OHLCV endpoint to render candlesticks here. {data.bars} bars loaded for {data.symbol}.
                </div>
                <MiniSparkline history={data.history} />
              </Card>
            </div>

            <div className="space-y-6">
              <Card title="Latest Fundamentals">
                {data.fundamentals ? (
                  <div className="space-y-3 text-sm">
                    <Row label="Filing date" value={data.fundamentals.filing_date ?? '—'} />
                    <Row label="Period end" value={data.fundamentals.period_end ?? '—'} />
                    <Row label="Revenue" value={data.fundamentals.revenue != null ? fmtBig(data.fundamentals.revenue) : '—'} />
                    <Row label="Net income" value={data.fundamentals.net_income != null ? fmtBig(data.fundamentals.net_income) : '—'} />
                    <Row label="EPS" value={data.fundamentals.eps_basic?.toFixed(2) ?? '—'} />
                    <Row label="P/E (est)" value={data.fundamentals.pe_ratio?.toFixed(2) ?? '—'} />
                    <Row label="Total assets" value={data.fundamentals.total_assets != null ? fmtBig(data.fundamentals.total_assets) : '—'} />
                    <Row label="Equity" value={data.fundamentals.stockholders_equity != null ? fmtBig(data.fundamentals.stockholders_equity) : '—'} />
                  </div>
                ) : (
                  <div className="text-gray-400 text-sm">No fundamentals ingested yet</div>
                )}
              </Card>

              <Card title="Key Indicators">
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(data.indicators).slice(0, 12).map(([k, v]) => (
                    <div key={k} className="bg-gray-50 rounded p-2">
                      <div className="text-[10px] text-gray-400 uppercase">{k}</div>
                      <div className="text-sm font-medium text-gray-800">{v.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>

          {/* Comparison */}
          {compare && (
            <Card title="Relative Performance vs Benchmarks (rebased to 100)">
              <div className="space-y-3">
                {Object.entries(compare.series).map(([s, points]) => {
                  if (points.length === 0) return null;
                  const first = points[0].value;
                  const last = points[points.length - 1].value;
                  const up = last >= first;
                  return (
                    <div key={s} className="flex items-center justify-between text-sm">
                      <span className="font-medium w-20">{s}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded overflow-hidden mx-3">
                        <div
                          className={`h-full ${up ? 'bg-primary-500' : 'bg-danger-500'}`}
                          style={{ width: `${Math.min(Math.abs((last / first - 1) * 1000), 100)}%` }}
                        />
                      </div>
                      <span className={`w-24 text-right font-semibold ${up ? 'text-primary-600' : 'text-danger-600'}`}>
                        {last.toFixed(1)} <span className="text-xs font-normal text-gray-400">({((last / first - 1) * 100).toFixed(1)}%)</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800">{value}</span>
    </div>
  );
}

function fmtBig(n: number): string {
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}

function MiniSparkline({ history }: { history: { close: number }[] }) {
  const closes = history.slice(-60).map(h => h.close);
  if (closes.length < 2) {
    return <div className="h-40 flex items-center justify-center text-gray-400 text-xs">Not enough data</div>;
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const points = closes.map((c, i) => {
    const x = (i / (closes.length - 1)) * 100;
    const y = 100 - ((c - min) / range) * 100;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const up = closes[closes.length - 1] >= closes[0];
  const color = up ? '#22c55e' : '#ef4444';

  return (
    <div className="h-40">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
        <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
      </svg>
    </div>
  );
}