import { useEffect, useState } from 'react';
import { dataApi } from '../services/api';
import { Card, Spinner, ErrorState, StatCard } from '../components/ui';
import type { DataHealthSummary, FundamentalsHealth, FeaturesHealth, OHLCVHealth } from '../types';

const UNIVERSE = ['AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'SPY', 'QQQ'];

export function DataHealth() {
  const [summary, setSummary] = useState<DataHealthSummary | null>(null);
  const [fundamentals, setFundamentals] = useState<FundamentalsHealth | null>(null);
  const [features, setFeatures] = useState<FeaturesHealth | null>(null);
  const [ohlcvBySymbol, setOhlcvBySymbol] = useState<Record<string, OHLCVHealth>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [s, f, feats] = await Promise.all([
        dataApi.summary().catch(() => null),
        dataApi.fundamentals().catch(() => null),
        dataApi.features().catch(() => null),
      ]);
      setSummary(s);
      setFundamentals(f);
      setFeatures(feats);

      const checks: Record<string, OHLCVHealth> = {};
      for (const symbol of UNIVERSE) {
        checks[symbol] = await dataApi.ohlcv(symbol, 30).catch(() => null as unknown as OHLCVHealth);
      }
      setOhlcvBySymbol(checks);
    } catch (e) {
      setError('Failed to load data health. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const fmtLag = (hours: number | null) => {
    if (hours == null) return '—';
    if (hours < 1) return `${Math.round(hours * 60)}m`;
    if (hours < 24) return `${hours.toFixed(1)}h`;
    return `${(hours / 24).toFixed(1)}d`;
  };

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Data Health</h1>
          <p className="text-gray-500">Ingestion freshness, coverage, and pipeline status</p>
        </div>
        <button
          onClick={load}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-sm font-medium"
        >
          Refresh
        </button>
      </header>

      {error && <ErrorState message={error} />}
      {loading && <Spinner />}

      {!loading && summary && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Symbols w/ Data" value={summary.ohlcv.symbols_with_data} />
            <StatCard label="Bars (7d)" value={summary.ohlcv.total_bars_7d} />
            <StatCard label="Ingestion Lag" value={fmtLag(summary.ohlcv.ingestion_lag_hours)} sublabel="time since last ingest" />
            <StatCard label="Scheduler" value={summary.scheduler.running ? 'Running' : 'Stopped'} tone={summary.scheduler.running ? 'positive' : 'negative'} />
          </div>

          {/* Scheduler jobs */}
          <Card title="Scheduled Jobs">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
                    <th className="py-2 pr-4">Job</th>
                    <th className="py-2 pr-4">Trigger</th>
                    <th className="py-2">Next Run</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.scheduler.jobs.map(job => (
                    <tr key={job.id} className="border-b border-gray-50">
                      <td className="py-2 pr-4 font-medium">{job.name}</td>
                      <td className="py-2 pr-4 text-gray-500">{job.trigger}</td>
                      <td className="py-2 text-gray-500">{job.next_run ? new Date(job.next_run).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                  {summary.scheduler.jobs.length === 0 && (
                    <tr><td colSpan={3} className="py-6 text-center text-gray-400">No scheduled jobs</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Per-symbol OHLCV freshness */}
          <Card title="OHLCV Freshness by Symbol (30d)">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-400 uppercase border-b border-gray-100">
                    <th className="py-2 pr-4">Symbol</th>
                    <th className="py-2 pr-4">Bars</th>
                    <th className="py-2 pr-4">Last Bar</th>
                    <th className="py-2 pr-4">Missing Days</th>
                    <th className="py-2">Complete</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(ohlcvBySymbol).map(([symbol, h]) => {
                    if (!h) return null;
                    return (
                      <tr key={symbol} className="border-b border-gray-50">
                        <td className="py-2 pr-4 font-medium">{symbol}</td>
                        <td className="py-2 pr-4">{h.bars_found}</td>
                        <td className="py-2 pr-4 text-gray-500">{h.last_bar ? new Date(h.last_bar).toLocaleDateString() : '—'}</td>
                        <td className="py-2 pr-4">{h.missing_trading_days}</td>
                        <td className="py-2">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${h.data_complete ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                            {h.data_complete ? 'OK' : 'GAPS'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Fundamentals coverage */}
          {fundamentals && (
            <Card title="Fundamentals Coverage (SEC)">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                <StatCard label="Symbols" value={fundamentals.total_symbols} />
                <StatCard label="Filings" value={fundamentals.total_filings} />
                <StatCard label="Latest Filing" value={fundamentals.latest_filing ?? '—'} />
                <StatCard label="Covered Symbols" value={fundamentals.coverage.length} />
              </div>
              <div className="overflow-x-auto max-h-72">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-400 uppercase border-b border-gray-100">
                      <th className="py-2 pr-3">Symbol</th>
                      <th className="py-2 pr-3">Filings</th>
                      <th className="py-2 pr-3">Net Income</th>
                      <th className="py-2 pr-3">Revenue</th>
                      <th className="py-2 pr-3">Assets</th>
                      <th className="py-2">Shares</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fundamentals.coverage.map(c => (
                      <tr key={c.symbol} className="border-b border-gray-50">
                        <td className="py-1.5 pr-3 font-medium">{c.symbol}</td>
                        <td className="py-1.5 pr-3">{c.filings}</td>
                        <td className="py-1.5 pr-3">{c.metrics_present.net_income > 0 ? '✓' : '✗'}</td>
                        <td className="py-1.5 pr-3">{c.metrics_present.revenue > 0 ? '✓' : '✗'}</td>
                        <td className="py-1.5 pr-3">{c.metrics_present.total_assets > 0 ? '✓' : '✗'}</td>
                        <td className="py-1.5">{c.metrics_present.shares_outstanding > 0 ? '✓' : '✗'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Features */}
          {features && (
            <Card title="ML Feature Store (ml_features_weekly)">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                <StatCard label="Symbols" value={features.symbols} />
                <StatCard label="Total Rows" value={features.total_rows} />
                <StatCard label="Latest Date" value={features.latest_as_of_date ?? '—'} />
                <StatCard label="Rows w/ Labels" value={features.feature_coverage.labels_fwd_ret_4w} />
              </div>
              <div className="text-xs text-gray-400">
                rsi_14 populated: {features.feature_coverage.rsi_14} • macd_hist populated: {features.feature_coverage.macd_hist}
              </div>
            </Card>
          )}
        </div>
      )}

      {!loading && !summary && !error && (
        <ErrorState message="Backend returned no health data" />
      )}
    </div>
  );
}