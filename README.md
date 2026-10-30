# Stock Agent - Algorithmic Trading Platform

A production-ready algorithmic trading system with paper trading, real-time data, and circuit breakers.

## Architecture

- **Backend**: FastAPI + PostgreSQL (TimescaleDB) + Redis + Alpaca Paper Trading
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Lightweight Charts
- **Infrastructure**: Docker Compose, Railway deployment

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Alpaca Paper Trading account (free)
- Neon PostgreSQL account (free) or local PostgreSQL
- Upstash Redis (free) or local Redis

### Environment Setup

1. Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

Required variables:
- `DATABASE_URL` - Neon PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `API_SECRET_KEY` - Generate with `openssl rand -hex 32`
- `ALPACA_API_KEY` - From Alpaca dashboard
- `ALPACA_SECRET_KEY` - From Alpaca dashboard

### Development

```bash
# Start all services
docker-compose up --build

# Backend API: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Database Migrations

```bash
# Run migrations
cd backend
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

## Features

### Phase 1 (Complete)
- ✅ Paper trading with Alpaca (REST + WebSocket IEX feed)
- ✅ Real-time quotes & trades via WebSocket
- ✅ Order management (market, limit, stop, stop-limit)
- ✅ Position tracking with real-time P&L
- ✅ Circuit breakers: kill switch, rate limits, drawdown, position/sector limits
- ✅ X-API-Key authentication on all mutation endpoints
- ✅ Redis-backed execution guards with persistence
- ✅ WebSocket auto-reconnect with exponential backoff
- ✅ Lightweight Charts for real-time visualization

### Phase 2 (Planned)
- 📊 SEC EDGAR XBRL parser for point-in-time fundamentals
- 📈 Local technical indicators via pandas-ta
- 🗄️ Point-in-time feature store with knowledge_timestamp

### Phase 3 (Planned)
- 🤖 VectorBT backtesting framework
- 🧠 XGBoost baseline models (weekly horizon)
- 📉 Walk-forward validation

### Phase 4 (Planned)
- 🔮 Advanced ML (LSTM, Stacking Ensemble)
- 📱 Full dashboard (Signals, Analysis, Backtest Lab)

## API Endpoints

### Account & Positions
- `GET /api/v1/account` - Account summary
- `GET /api/v1/positions` - All positions
- `POST /api/v1/positions/{symbol}/close` - Close position
- `POST /api/v1/positions/close-all` - Close all positions

### Orders
- `GET /api/v1/orders` - List orders
- `POST /api/v1/orders` - Place order
- `POST /api/v1/orders/{id}/cancel` - Cancel order

### Circuit Breakers
- `GET /api/v1/guards` - Guard status
- `POST /api/v1/guards/{type}` - Enable/disable guard
- `POST /api/v1/kill-switch` - Toggle kill switch

### WebSocket
- `WS /api/v1/stream?api_key=...` - Real-time quotes & trades

### Market Data
- `GET /api/v1/quotes?symbols=AAPL,NVDA` - Latest quotes

## Order Types Supported

| Type | Parameters |
|------|------------|
| Market | symbol, side, qty |
| Limit | symbol, side, qty, limit_price |
| Stop | symbol, side, qty, stop_price |
| Stop Limit | symbol, side, qty, limit_price, stop_price |

Time in Force: `day`, `gtc`, `opg`, `cls`, `ioc`, `fok`

## Circuit Breaker Config

| Guard | Default | Description |
|-------|---------|-------------|
| Kill Switch | Enabled | Blocks all new orders |
| Rate Limit | 10/min | Max orders per minute |
| Drawdown | 2% | Max daily drawdown |
| Position Limit | 10% | Max per-position allocation |
| Sector Limit | 25% | Max sector allocation |

## Deployment

### Railway (Recommended)
1. Connect GitHub repo to Railway
2. Add environment variables
3. Deploy backend and frontend as separate services
4. Add PostgreSQL (Neon) and Redis (Upstash) add-ons

### Docker
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Security

- All mutation endpoints require `X-API-Key` header
- API key must match `API_SECRET_KEY` in environment
- CORS configured for localhost:3000 only
- Alpaca paper trading only (no live trading)

## Project Structure

```
stock-agent/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI routes
│   │   ├── core/            # Config, DB, Redis, Security
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # Business logic
│   │   └── main.py          # App entry point
│   ├── alembic/             # Migrations
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── pages/           # Page components
│   │   ├── hooks/           # Custom hooks
│   │   ├── services/        # API clients
│   │   ├── store/           # Zustand stores
│   │   └── types/           # TypeScript types
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## License

MIT