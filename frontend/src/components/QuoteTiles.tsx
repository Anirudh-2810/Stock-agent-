import { useTradingStore } from '../store/tradingStore';

function formatPrice(val: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function formatSize(val: number): string {
  if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
  if (val >= 1000) return `${(val / 1000).toFixed(1)}K`;
  return val.toString();
}

export function QuoteTiles() {
  const quotes = useTradingStore(s => s.quotes);
  const symbols = ['AAPL', 'NVDA', 'SPY', 'QQQ', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM'];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Live Quotes (IEX)</h2>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {symbols.map(symbol => {
          const quote = quotes.get(symbol);
          if (!quote) {
            return (
              <div key={symbol} className="p-3 bg-gray-50 rounded border border-gray-200 animate-pulse">
                <div className="font-medium text-gray-500">{symbol}</div>
                <div className="text-2xl font-mono text-gray-300">--.--</div>
              </div>
            );
          }

          const mid = (quote.bid_price + quote.ask_price) / 2;
          const spread = quote.ask_price - quote.bid_price;
          const spreadPct = (spread / mid) * 100;

          return (
            <div key={symbol} className="p-3 bg-gray-50 rounded border border-gray-200 hover:border-primary-300 transition">
              <div className="flex justify-between items-baseline mb-1">
                <span className="font-medium text-gray-800">{symbol}</span>
                <span className="text-xs text-gray-400">IEX</span>
              </div>
              <div className="text-2xl font-mono font-semibold text-gray-900 mb-1">
                {formatPrice(mid)}
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>Bid: {formatPrice(quote.bid_price)} × {formatSize(quote.bid_size)}</span>
                <span>Ask: {formatPrice(quote.ask_price)} × {formatSize(quote.ask_size)}</span>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Spread: {formatPrice(spread)} ({spreadPct.toFixed(3)}%)
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}