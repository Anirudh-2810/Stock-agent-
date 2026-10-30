import { NavLink, Outlet } from 'react-router-dom';
import { useTradingStore } from '../store/tradingStore';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: '◉' },
  { to: '/signals', label: 'Signals', icon: '⚡' },
  { to: '/analysis', label: 'Analysis', icon: '📈' },
  { to: '/backtest', label: 'Backtest Lab', icon: '🧪' },
  { to: '/health', label: 'Data Health', icon: '💊' },
  { to: '/trading', label: 'Paper Trading', icon: '🖥️' },
];

export function DashboardLayout() {
  const isConnected = useTradingStore(s => s.isConnected);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="w-56 bg-slate-900 text-slate-300 flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-slate-800">
          <div className="text-lg font-bold text-white">Stock Agent</div>
          <div className="text-xs text-slate-500 mt-1">Algorithmic Research Console</div>
        </div>

        <nav className="flex-1 py-4">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white border-r-2 border-primary-500'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`
              }
            >
              <span className="w-4 text-center">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-slate-800 text-xs">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span>{isConnected ? 'Live Feed Connected' : 'Feed Disconnected'}</span>
          </div>
          <div className="text-slate-600 mt-2">Alpaca Paper • IEX</div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}