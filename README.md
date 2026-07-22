# Cloud-Native Institutional Trading Engine

> Master engineering specification for a production-grade, event-driven quantitative trading engine.

## Overview

This project is a cloud-native, event-driven algorithmic trading engine for tokenized US equities. It emphasizes modularity, reliability, recoverability, and low operational cost.

## Core Stack

### Backend
- Python 3.13
- FastAPI
- asyncio
- httpx
- websockets
- APScheduler
- SQLAlchemy (async)
- Pydantic v2
- Polars
- NumPy

### Frontend
- Next.js
- React
- Tailwind CSS
- shadcn/ui
- Hosted on Vercel

### Infrastructure
- Backend hosted on Render
- Neon PostgreSQL
- In-memory cache using cachetools (no Redis)

## Broker Architecture

- Execution Broker: Bybit TradFi
- Separate Market Data Provider alpaca market
- Broker abstraction layer.

## Strategies

### Strategy 1 – Opening Range Breakout
- Scan 30–40 active symbols
- Premarket gap, volume, news, unusual activity
- Load 14-day 1-minute history
- Compute RVOL
- Build 5-minute opening range
- Execute breakout trades

### Strategy 2 – Noise Boundary Breakout
- SPY / QQQ
- Statistical envelope
- ATR
- Breakout trading

### Strategy 3 – First Hour / Last Hour
- Determine daily bias
- Enter at 15:30 ET
- Exit at 16:00 ET

## Core Services

- Market Data Service
- Broker Service
- Market Calendar Service
- Time Service
- Event Bus
- Strategy Manager
- Risk Engine
- Order Manager
- Position Manager
- Portfolio Manager
- Recovery Service
- State Recovery Service
- Logging Service
- Analytics Service
- Notification Service
- Dashboard API

## Operational Features

- Automatic failure recovery
- State reconstruction
- Position synchronization
- Configurable risk engine
- UTC-based time management
- Structured logging
- Performance analytics

## Dashboard

- Engine
- Strategies
- Scanner
- Orders
- Portfolio
- Analytics
- Logs
- Risk
- Settings
- Notifications

## Engineering Principles

- SOLID
- Clean Architecture
- Async-first
- Dependency Injection
- Strong typing
- Low coupling
- High cohesion
- Testability
