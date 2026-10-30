import { create } from 'zustand';
import type { PositionResponse, AccountResponse, OrderResponse, GuardStatus, QuoteData, TradeData } from '../types';

interface TradingState {
  account: AccountResponse | null;
  positions: PositionResponse[];
  orders: OrderResponse[];
  guards: Record<string, GuardStatus>;
  quotes: Map<string, QuoteData>;
  trades: TradeData[];
  isConnected: boolean;
  killSwitchActive: boolean;
  
  setAccount: (account: AccountResponse) => void;
  setPositions: (positions: PositionResponse[]) => void;
  setOrders: (orders: OrderResponse[]) => void;
  addOrder: (order: OrderResponse) => void;
  updateOrder: (order: OrderResponse) => void;
  setGuards: (guards: Record<string, GuardStatus>) => void;
  updateGuard: (guardType: string, isActive: boolean) => void;
  setKillSwitch: (active: boolean) => void;
  setQuotes: (quotes: QuoteData[]) => void;
  updateQuote: (quote: QuoteData) => void;
  addTrade: (trade: TradeData) => void;
  setConnected: (connected: boolean) => void;
  reset: () => void;
}

export const useTradingStore = create<TradingState>((set) => ({
  account: null,
  positions: [],
  orders: [],
  guards: {},
  quotes: new Map(),
  trades: [],
  isConnected: false,
  killSwitchActive: false,

  setAccount: (account) => set({ account }),
  setPositions: (positions) => set({ positions }),
  setOrders: (orders) => set({ orders }),
  addOrder: (order) => set((state) => ({ orders: [order, ...state.orders] })),
  updateOrder: (order) => set((state) => ({
    orders: state.orders.map(o => o.id === order.id ? order : o)
  })),
  setGuards: (guards) => set({ guards }),
  updateGuard: (guardType, isActive) => set((state) => ({
    guards: { ...state.guards, [guardType]: { ...state.guards[guardType], is_active: isActive } }
  })),
  setKillSwitch: (active) => set({ killSwitchActive: active }),
  setQuotes: (quotes) => set((state) => {
    const newQuotes = new Map(state.quotes);
    quotes.forEach(q => newQuotes.set(q.symbol, q));
    return { quotes: newQuotes };
  }),
  updateQuote: (quote) => set((state) => {
    const newQuotes = new Map(state.quotes);
    newQuotes.set(quote.symbol, quote);
    return { quotes: newQuotes };
  }),
  addTrade: (trade) => set((state) => ({ trades: [trade, ...state.trades].slice(0, 100) })),
  setConnected: (connected) => set({ isConnected: connected }),
  reset: () => set({
    account: null,
    positions: [],
    orders: [],
    guards: {},
    quotes: new Map(),
    trades: [],
    isConnected: false,
    killSwitchActive: false,
  }),
}));