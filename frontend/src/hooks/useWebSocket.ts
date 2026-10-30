import { useEffect, useCallback } from 'react';
import { wsService } from '../services/websocket';
import { useTradingStore } from '../store/tradingStore';
import type { WSMessage, QuoteData, TradeData } from '../types';

export function useWebSocketConnection() {
  const setConnected = useTradingStore((s) => s.setConnected);
  const updateQuote = useTradingStore((s) => s.updateQuote);
  const addTrade = useTradingStore((s) => s.addTrade);
  const setAccount = useTradingStore((s) => s.setAccount);
  const setPositions = useTradingStore((s) => s.setPositions);
  const setOrders = useTradingStore((s) => s.setOrders);

  const handleMessage = useCallback((message: WSMessage) => {
    switch (message.type) {
      case 'quote':
        updateQuote(message.data as QuoteData);
        break;
      case 'trade':
        addTrade(message.data as TradeData);
        break;
      case 'account_update':
        setAccount(message.data);
        break;
      case 'position_update':
        setPositions(message.data);
        break;
      case 'order_update':
        setOrders(message.data);
        break;
    }
  }, [setAccount, setPositions, setOrders, updateQuote, addTrade]);

  useEffect(() => {
    let mounted = true;

    const connect = async () => {
      try {
        await wsService.connect();
        if (mounted) setConnected(true);
      } catch (e) {
        console.error('WS connect failed:', e);
        if (mounted) setConnected(false);
      }
    };

    const unsubscribe = wsService.subscribe(handleMessage);
    connect();

    return () => {
      mounted = false;
      unsubscribe();
      wsService.disconnect();
      setConnected(false);
    };
  }, [handleMessage, setConnected]);
}

export function useReconnectingWebSocket() {
  const isConnected = wsService.isConnected();
  return isConnected;
}