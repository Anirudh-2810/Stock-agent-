import { useState } from 'react';
import { guardsApi } from '../services/api';
import { useTradingStore } from '../store/tradingStore';
import type { GuardStatus } from '../types';

export function KillSwitch() {
  const killSwitchActive = useTradingStore(s => s.killSwitchActive);
  const guards = useTradingStore(s => s.guards);
  const setKillSwitch = useTradingStore(s => s.setKillSwitch);
  const setGuards = useTradingStore(s => s.setGuards);
  const [loading, setLoading] = useState(false);

  const handleToggle = async () => {
    setLoading(true);
    try {
      const result = await guardsApi.killSwitch(!killSwitchActive);
      setKillSwitch(result.activated);
      // Refresh all guards
      const guardsData = await guardsApi.get();
      setGuards(guardsData);
    } catch (err) {
      console.error('Kill switch toggle failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const guardList: { key: string; label: string; guard?: GuardStatus }[] = [
    { key: 'kill_switch', label: 'Kill Switch' },
    { key: 'rate_limit', label: 'Rate Limit (10/min)' },
    { key: 'drawdown', label: 'Daily Drawdown (2%)' },
    { key: 'position_limit', label: 'Position Limit (10%)' },
    { key: 'sector_limit', label: 'Sector Limit (25%)' },
  ];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Circuit Breakers</h2>
      
      <div className="space-y-4">
        {guardList.map(({ key, label }) => {
          const guard = guards[key];
          const isActive = guard?.is_active ?? true;
          const triggered = guard?.trigger_count ?? 0;
          
          return (
            <div key={key} className="flex items-center justify-between p-3 bg-gray-50 rounded">
              <div className="flex items-center gap-3">
                <label className="flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={() => key !== 'kill_switch' && guardsApi.update(key, { is_active: !isActive })}
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                    disabled={key === 'kill_switch'}
                  />
                  <span className="ml-2 font-medium">{label}</span>
                </label>
              </div>
              <div className="flex items-center gap-4">
                {triggered > 0 && (
                  <span className="text-xs text-yellow-600 bg-yellow-100 px-2 py-1 rounded">
                    Triggered: {triggered}
                  </span>
                )}
                <span className={`text-sm font-mono ${isActive ? 'text-primary-600' : 'text-danger-600'}`}>
                  {isActive ? 'ACTIVE' : 'DISABLED'}
                </span>
              </div>
            </div>
          );
        })}

        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={handleToggle}
            disabled={loading}
            className={`w-full py-3 rounded-md font-medium text-white transition ${
              killSwitchActive 
                ? 'bg-primary-600 hover:bg-primary-700' 
                : 'bg-danger-600 hover:bg-danger-700'
            } disabled:opacity-50`}
          >
            {loading ? 'Toggling...' : killSwitchActive ? 'DEACTIVATE KILL SWITCH' : 'ACTIVATE KILL SWITCH'}
          </button>
          <p className="text-xs text-gray-500 text-center mt-2">
            {killSwitchActive 
              ? 'Kill switch ACTIVE - All new orders blocked. Existing positions can still be closed.' 
              : 'Kill switch INACTIVE - Normal trading enabled.'}
          </p>
        </div>
      </div>
    </div>
  );
}