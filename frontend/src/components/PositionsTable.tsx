import { positionsApi } from '../services/api';
import { useTradingStore } from '../store/tradingStore';
import type { PositionResponse } from '../types';

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function formatPct(val: number): string {
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

function formatNumber(val: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

export function PositionsTable() {
  const positions = useTradingStore(s => s.positions);
  const quotes = useTradingStore(s => s.quotes);

  if (positions.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Positions</h2>
        <p className="text-gray-500 text-center py-8">No open positions</p>
      </div>
    );
  }

  const totalPL = positions.reduce((sum, p) => sum + p.unrealized_pl, 0);
  const totalValue = positions.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">Positions ({positions.length})</h2>
        <div className="flex gap-4 text-sm">
          <span className={`font-mono ${totalPL >= 0 ? 'text-primary-600' : 'text-danger-600'}`}>
            Total P&L: {formatCurrency(totalPL)}
          </span>
          <span className="font-mono text-gray-700">
            Value: {formatCurrency(totalValue)}
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-200">
              <th className="pb-2 pr-4">Symbol</th>
              <th className="pb-2 pr-4 text-right">Qty</th>
              <th className="pb-2 pr-4 text-right">Avg Entry</th>
              <th className="pb-2 pr-4 text-right">Current</th>
              <th className="pb-2 pr-4 text-right">Market Value</th>
              <th className="pb-2 pr-4 text-right">P&L</th>
              <th className="pb-2 pr-4 text-right">P&L %</th>
              <th className="pb-2 pr-4">Day Change</th>
              <th className="pb-2 pr-4"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {positions.map((pos: PositionResponse) => {
              const quote = quotes.get(pos.symbol);
              const currentPrice = quote 
                ? (Number(quote.bid_price) + Number(quote.ask_price)) / 2 
                : pos.current_price;
              const dayChangePct = pos.lastday_price 
                ? ((currentPrice - pos.lastday_price) / pos.lastday_price) * 100 
                : 0;

              return (
                <tr key={pos.id} className="hover:bg-gray-50">
                  <td className="py-3 pr-4 font-medium">{pos.symbol}</td>
                  <td className="py-3 pr-4 text-right font-mono">
                    {formatNumber(pos.qty)} ({pos.side})
                  </td>
                  <td className="py-3 pr-4 text-right font-mono">
                    {formatCurrency(pos.avg_entry_price)}
                  </td>
                  <td className="py-3 pr-4 text-right font-mono">
                    {formatCurrency(currentPrice)}
                  </td>
                  <td className="py-3 pr-4 text-right font-mono">
                    {formatCurrency(pos.market_value)}
                  </td>
                  <td className={`py-3 pr-4 text-right font-mono ${pos.unrealized_pl >= 0 ? 'text-primary-600' : 'text-danger-600'}`}>
                    {formatCurrency(pos.unrealized_pl)}
                  </td>
                  <td className={`py-3 pr-4 text-right font-mono ${pos.unrealized_plpc >= 0 ? 'text-primary-600' : 'text-danger-600'}`}>
                    {formatPct(pos.unrealized_plpc * 100)}
                  </td>
                  <td className={`py-3 pr-4 text-right font-mono ${dayChangePct >= 0 ? 'text-primary-600' : 'text-danger-600'}`}>
                    {formatPct(dayChangePct)}
                  </td>
                  <td className="py-3 pr-4">
                    <button
                      onClick={async () => {
                        await positionsApi.close(pos.symbol);
                      }}
                      className="text-xs px-2 py-1 bg-danger-100 text-danger-700 rounded hover:bg-danger-200 transition"
                    >
                      Close
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}