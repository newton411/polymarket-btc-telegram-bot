# RECON HFT — Polymarket 5-Min BTC Trading Bot

A production-grade HFT bot that targets 5-minute Bitcoin Up/Down prediction markets on Polymarket using a Bayesian Z-Score edge detection strategy.

## Features

- **Bayesian Z-Score Strategy** — Models BTC resolution probability using volatility-adjusted time decay
- **Stop-Loss & Take-Profit** — Automated risk management based on probability shifts (default: SL 5%, TP 15%)
- **Real-time P&L Alerts** — Threshold-triggered Telegram notifications for significant gains/losses
- **Backtesting** — Simulate strategy against real historical Binance OHLCV data from inside Telegram
- **Deep Performance Stats** — Win rate, Sharpe ratio, max drawdown, profit factor, exit breakdown
- **Dry Run Mode** — Test all logic without placing real orders

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Open the live auto-refreshing dashboard |
| `/status` | Snapshot of current portfolio & bot state |
| `/stats` | **Deep performance stats**: win rate, Sharpe ratio, drawdown, profit factor |
| `/backtest [n]` | Run backtest on last `n` 1-minute candles (default 1500, max 3000) |
| `/positions` | List all currently open positions |
| `/pause` | Pause trading engine |
| `/resume` | Resume trading engine |
| `/setthreshold <val>` | Set minimum edge required to open a trade (e.g. `0.10`) |
| `/setsl <val>` | Set stop-loss probability shift threshold (e.g. `0.05`) |
| `/settp <val>` | Set take-profit probability shift threshold (e.g. `0.15`) |
| `/setpnl <val>` | Set P&L alert threshold in USDC (e.g. `5.0`) |

### Dashboard Inline Buttons

| Button | Action |
|--------|--------|
| 🔄 Refresh | Re-render the latest dashboard state |
| ⏸ Pause/Resume | Toggle the trading engine |
| 📊 Deep Stats | Send full performance report |
| 📂 Positions | List open positions |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_ALLOWED_USER_ID` | Your Telegram numeric user ID |
| `POLYMARKET_ADDRESS` | Your API wallet address (provided) |
| `POLYMARKET_PK` | Your private key for signing orders |
| `POLYMARKET_API_KEY` | CLOB API key |
| `POLYMARKET_API_PASSPHRASE` | CLOB passphrase |
| `POLYMARKET_API_SECRET` | CLOB secret |
| `TRADING_MODE` | `DRY_RUN` or `LIVE` |
| `EDGE_THRESHOLD` | Min edge to enter trade (default `0.10`) |
| `STOP_LOSS_PCT` | SL threshold (default `0.05`) |
| `TAKE_PROFIT_PCT` | TP threshold (default `0.15`) |
| `PNL_ALERT_THRESHOLD` | USDC delta to trigger alert (default `5.0`) |
| `INITIAL_BALANCE` | Starting balance for tracking (default `5000.0`) |

### 3. Run

```bash
python -m bot.main
```

### 4. Backtest (standalone CLI)

```bash
python -m bot.backtest --limit 2000 --edge 0.10 --sl 0.05 --tp 0.15
```

## Strategy

The bot computes a **Bayesian implied probability** for each 5-minute BTC market:

```
Z = (BTC_price − Strike) / (σ × √(t/T))
P(Yes) ≈ 0.5 + Z/2            (linear CDF approximation)
Edge   = P(Yes) − Market_Price
```

Where:
- `σ = 100 USD` — volatility proxy per 5 minutes
- `t/T` — fraction of time remaining until expiry
- Entry when `Edge > threshold`

Positions are monitored every 3 seconds. They close via:
- **Stop-Loss** when current probability drops below `entry × (1 − SL_pct)`
- **Take-Profit** when current probability rises above `entry + (1 − entry) × TP_pct`
- **Expiry** — settles at 1.0 (win) or 0.0 (loss) at market resolution

## Wallet

```
Address: 0xc7b9939135F5143D5b9eB968cf6f93566E31ff52
Note: This address is for API use only. Do NOT send funds here.
```

API credentials are obtained from: https://docs.polymarket.com/api-reference/authentication
