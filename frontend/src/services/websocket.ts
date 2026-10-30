import type { WSMessage } from '../types';

type MessageHandler = (message: WSMessage) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private apiKey: string;
  private handlers: Set<MessageHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private isIntentionalClose = false;
  private messageBuffer: WSMessage[] = [];

  constructor() {
    this.url = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000') + '/api/v1/stream';
    this.apiKey = import.meta.env.VITE_API_KEY || '';
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      this.isIntentionalClose = false;
      const wsUrl = `${this.url}?api_key=${this.apiKey}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WS connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.flushBuffer();
        resolve();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          this.handlers.forEach(h => h(message));
        } catch (e) {
          console.error('WS message parse error:', e);
        }
      };

      this.ws.onclose = (event) => {
        console.log(`WS closed: ${event.code} ${event.reason}`);
        if (!this.isIntentionalClose) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('WS error:', error);
        if (this.reconnectAttempts === 0) {
          reject(error);
        }
      };
    });
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1), this.maxReconnectDelay);
    const jitter = Math.random() * 1000;
    
    console.log(`Reconnecting in ${Math.round(delay + jitter)}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => {
      this.connect().catch(() => {});
    }, delay + jitter);
  }

  private flushBuffer() {
    while (this.messageBuffer.length > 0) {
      const msg = this.messageBuffer.shift();
      if (msg) {
        this.handlers.forEach(h => h(msg));
      }
    }
  }

  disconnect() {
    this.isIntentionalClose = true;
    this.ws?.close(1000, 'Intentional close');
    this.ws = null;
  }

  subscribe(handler: MessageHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  get readyState() {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsService = new WebSocketService();

export function useWebSocket(onMessage: (msg: WSMessage) => void) {
  if (typeof window !== 'undefined') {
    const unsubscribe = wsService.subscribe(onMessage);
    return unsubscribe;
  }
  return () => {};
}