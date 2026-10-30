import { useTradingStore } from '../store/tradingStore';

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

export function PnLCards() {
  const account = useTradingStore(s => s.account);

  if (!account) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1,2,3,4].map(i => (
          <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-8 bg-gray-200 rounded w-1/2"></div>
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    { label: 'Equity', value: formatCurrency(account.equity), class: '' },
    { label: 'Cash', value: formatCurrency(account.cash), class: '' },
    { label: 'Buying Power', value: formatCurrency(account.buying_power), class: '' },
    { 
      label: 'Daily P&L', 
      value: `${formatCurrency(account.daily_pl)} (${formatPct(account.daily_plpc * 100)})`, 
      class: account.daily_pl >= 0 ? 'text-primary-600' : 'text-danger-600' 
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, i) => (
        <div key={i} className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500 mb-1">{card.label}</p>
          <p className={`text-2xl font-mono font-semibold ${card.class}`}>{card.value}</p>
        </div>
      ))}
    </div>
  );
}