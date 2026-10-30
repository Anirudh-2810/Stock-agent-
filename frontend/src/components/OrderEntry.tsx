import React, { useState } from 'react';
import { useTradingStore } from '../store/tradingStore';
import { ordersApi } from '../services/api';
import type { OrderRequest } from '../types';

const SYMBOLS = ['AAPL', 'NVDA', 'SPY', 'QQQ', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'JPM'];

export function OrderEntry() {
  const [symbol, setSymbol] = useState('AAPL');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [type, setType] = useState<'market' | 'limit' | 'stop' | 'stop_limit'>('market');
  const [qty, setQty] = useState('1');
  const [limitPrice, setLimitPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [tif, setTif] = useState<'day' | 'gtc'>('day');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const guards = useTradingStore(s => s.guards);
  const killSwitch = guards.kill_switch?.is_active;
  const canTrade = !killSwitch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    const order: OrderRequest = {
      symbol: symbol.toUpperCase(),
      side,
      type,
      time_in_force: tif,
      qty: parseFloat(qty),
      limit_price: type !== 'market' && limitPrice ? parseFloat(limitPrice) : undefined,
      stop_price: (type === 'stop' || type === 'stop_limit') && stopPrice ? parseFloat(stopPrice) : undefined,
    };

    try {
      await ordersApi.place(order);
      setSuccess('Order placed successfully');
      setQty('1');
      setLimitPrice('');
      setStopPrice('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to place order');
    } finally {
      setLoading(false);
    }
  };

  const showLimit = type === 'limit' || type === 'stop_limit';
  const showStop = type === 'stop' || type === 'stop_limit';

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Order Entry</h2>
      
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded text-sm">
          {success}
        </div>
      )}
      {killSwitch && (
        <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 text-yellow-700 rounded text-sm">
          ⚠ Kill Switch Active - Orders Blocked
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            >
              {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Side</label>
            <select
              value={side}
              onChange={(e) => setSide(e.target.value as 'buy' | 'sell')}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            >
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Order Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as any)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            disabled={!canTrade}
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
            <option value="stop_limit">Stop Limit</option>
          </select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
            <input
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              step="0.01"
              min="0.01"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Time in Force</label>
            <select
              value={tif}
              onChange={(e) => setTif(e.target.value as any)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            >
              <option value="day">Day</option>
              <option value="gtc">GTC</option>
            </select>
          </div>
        </div>

        {showLimit && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Limit Price</label>
            <input
              type="number"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              step="0.01"
              min="0.01"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            />
          </div>
        )}

        {showStop && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Stop Price</label>
            <input
              type="number"
              value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)}
              step="0.01"
              min="0.01"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={!canTrade}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !canTrade}
          className={`w-full py-3 rounded-md font-medium text-white ${
            side === 'buy' ? 'bg-primary-600 hover:bg-primary-700' : 'bg-danger-600 hover:bg-danger-700'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {loading ? 'Placing...' : `${side.toUpperCase()} ${symbol}`}
        </button>
      </form>
    </div>
  );
}