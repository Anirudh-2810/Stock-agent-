import { useEffect, useState } from 'react';
import { useWebSocketConnection } from '../hooks/useWebSocket';
import { accountApi, positionsApi, ordersApi, guardsApi } from '../services/api';
import { useTradingStore } from '../store/tradingStore';
import { OrderEntry } from '../components/OrderEntry';
import { PositionsTable } from '../components/PositionsTable';
import { PnLCards } from '../components/PnLCards';
import { KillSwitch } from '../components/KillSwitch';
import { QuoteTiles } from '../components/QuoteTiles';
import { Chart } from '../components/Chart';
import type { ChartData } from '../hooks/useChart';
import type { UTCTimestamp } from 'lightweight-charts';

export function PaperTrading() {
  const { setAccount, setPositions, setOrders, setGuards } = useTradingStore();
  const isConnected = useTradingStore(s => s.isConnected);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');

  useWebSocketConnection();

  useEffect(() => {
    const loadInitial = async () => {
      try {
        const [account, positions, orders, guards] = await Promise.all([
          accountApi.get(),
          positionsApi.get(),
          ordersApi.get(),
          guardsApi.get(),
        ]);
        setAccount(account);
        setPositions(positions);
        setOrders(orders);
        setGuards(guards);
      } catch (e) {
        console.error('Failed to load initial data:', e);
      }
    };
    loadInitial();
  }, [setAccount, setPositions, setOrders, setGuards]);

  // Generate mock chart data for demo
  useEffect(() => {
    const generateMockData = (): ChartData[] => {
      const now = Date.now();
      const data: ChartData[] = [];
      let price = 150;
      for (let i = 100; i >= 0; i--) {
        const time = (now - i * 3600000) / 1000 as UTCTimestamp;
        const change = (Math.random() - 0.5) * 2;
        price = Math.max(100, price + change);
        data.push({
          time,
          open: price - Math.random(),
          high: price + Math.random(),
          low: price - Math.random(),
          close: price,
          volume: Math.random() * 1000000,
        });
      }
      return data;
    };
    setChartData(generateMockData());
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Paper Trading</h1>
            <p className="text-gray-500">Alpaca Paper Account • IEX Feed</p>
          </div>
          <div className="flex items-center gap-4">
            <span className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
              isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>

        {/* P&L Cards */}
        <PnLCards />

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Order Entry & Positions */}
          <div className="lg:col-span-1 space-y-6">
            <OrderEntry />
            <PositionsTable />
          </div>

          {/* Right Column - Chart & Quotes */}
          <div className="lg:col-span-2 space-y-6">
            <div>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Chart</h2>
                <select
                  value={selectedSymbol}
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="px-3 py-1 border border-gray-300 rounded text-sm"
                >
                  {['AAPL', 'NVDA', 'SPY', 'QQQ', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM'].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <Chart data={chartData} height={400} />
            </div>
            <QuoteTiles />
          </div>
        </div>

        {/* Circuit Breakers */}
        <KillSwitch />
      </div>
    </div>
  );
}