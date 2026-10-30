import { useEffect, useState } from 'react';
import { useTradingStore } from '../store/tradingStore';
import { accountApi, analysisApi, signalsApi } from '../services/api';
import { StatCard, Card, ErrorState, Badge } from '../components/ui';
import type { MarketOverview, PortfolioSignalSummary } from '../types';

const UNIVERSE = 'AAPL,NVDA,MSFT,GOOGL,AMZN,META,TSLA,SPY,QQQ';

export function Overview() {
  const account = useTradingStore(s => s.account);
  const setAccount = useTradingStore(s => s.setAccount);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [signals, setSignals] = useState<PortfolioSignalSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const [acct, ov, sig] = await Promise.all([
          accountApi.get().catch(() => null),
          analysisApi.overview(UNIVERSE, 30).catch(() => null),
          signalsApi.summary(UNIVERSE).catch(() => null),
        ]);
        if (acct) setAccount(acct);
        setOverview(ov);
        setSignals(sig);
      } catch (e) {
        setError('Failed to load overview data. Is the backend running?');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [setAccount]);

  const fmt = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <p className="text-gray-500">Account health, market pulse, and trading signals at a glance</p>
      </header>

      {error && <ErrorState message={error} />}

      {/* Account stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Equity" value={fmt(account?.equity ?? 0)} sublabel="Total account value" />
        <StatCard label="Cash" value={fmt(account?.cash ?? 0)} sublabel="Available" />
        <StatCard label="Buying Power" value={fmt(account?.buying_power ?? 0)} sublabel="Margin available" />
        <StatCard
          label="Daily P/L"
          value={`${(account?.daily_pl ?? 0) >= 0 ? '+' : ''}${fmt(account?.daily_pl ?? 0)}`}
          sublabel={`${((account?.daily_plpc ?? 0) * 100).toFixed(2)}% today`}
          tone={(account?.daily_pl ?? 0) >= 0 ? 'positive' : 'negative'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Market indexes */}
        <Card title="Market Indexes">
          {loading ? (
            <div className="text-gray-400 text-sm">Loading...</div>
          ) : !overview || overview.indexes.length === 0 ? (
            <div className="text-gray-400 text-sm">No index data available</div>
          ) : (
            <div className="space-y-3">
              {overview.indexes.map(idx => (
                <div key={idx.symbol} className="flex items-center justify-between">
                  <span className="font-medium text-gray-700">{idx.symbol}</span>
                  <span className="text-sm text-gray-500">{idx.close.toFixed(2)}</span>
                  <span className={`text-sm font-semibold ${idx.change_pct >= 0 ? 'text-primary-600' : 'text-danger-600'}`}>
                    {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Signal summary */}
        <Card title="Portfolio Signal Distribution">
          {loading ? (
            <div className="text-gray-400 text-sm">Loading...</div>
          ) : signals && signals.total > 0 ? (
            <div>
              <div className="grid grid-cols-4 gap-3 mb-4">
                <StatCard label="Strong Buy" value={signals.strong_buys} tone="positive" />
                <StatCard label="Buy" value={signals.buys} tone="positive" />
                <StatCard label="Sell" value={signals.sells} tone="negative" />
                <StatCard label="Avg Score" value={signals.avg_score.toFixed(2)} />
              </div>
              <div className="space-y-2">
                {signals.top_picks.slice(0, 3).map(s => (
                  <div key={s.symbol} className="flex items-center justify-between text-sm">
                    <span className="font-medium text-gray-700">{s.symbol}</span>
                    <Badge tone={s.action.toLowerCase() as 'buy' | 'sell' | 'hold'}>{s.action}</Badge>
                    <span className="text-gray-500">score {s.score.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-gray-400 text-sm">No signal data available</div>
          )}
        </Card>
      </div>

      {/* Top movers */}
      <Card title="Top Movers Over Window">
        {loading ? (
          <div className="text-gray-400 text-sm">Loading...</div>
        ) : overview && overview.best.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-medium text-gray-400 mb-2">BEST PERFORMERS</div>
              <div className="space-y-1.5">
                {overview.best.map(m => (
                  <div key={m.symbol} className="flex justify-between text-sm">
                    <span className="font-medium">{m.symbol}</span>
                    <span className="text-primary-600 font-semibold">+{m.change_pct.toFixed(2)}%</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs font-medium text-gray-400 uppercase mb-2">WORST PERFORMERS</div>
              <div className="space-y-1.5">
                {overview.worst.map(m => (
                  <div key={m.symbol} className="flex justify-between text-sm">
                    <span className="font-medium">{m.symbol}</span>
                    <span className="text-danger-600 font-semibold">{m.change_pct.toFixed(2)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-gray-400 text-sm">No mover data</div>
        )}
      </Card>
    </div>
  );
}