# RECON HFT — Polymarket 5-Min BTC Bot

A high-frequency trading bot that targets 5-minute Bitcoin prediction markets on Polymarket using a Bayesian Z-Score edge-detection strategy, controlled via a live Telegram dashboard.

---

## Features

| Feature | Details |
|---|---|
| **Bayesian Z-Score Engine** | Models resolution probability based on BTC spot price, strike, and time-to-expiry |
| **Stop-Loss / Take-Profit** | Automated risk management via configurable probability-shift thresholds |
| **Backtesting Module** | Simulate strategy on real Binance OHLCV history; full Sharpe, drawdown, win-rate report |
| **Real-Time PnL Alerts** | Telegram notification whenever cumulative PnL crosses a configurable threshold |
| **Deep Stats Dashboard** | Win rate, avg win/loss, profit factor, max drawdown, Sharpe ratio, exit breakdown |
| **DRY_RUN Mode** | Full simulation without placing real orders — safe for testing |
| **Live Positions Tracking** | Dashboard shows up to 3 open positions with side, entry price, and age |

---

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Open the live dashboard with inline buttons |
| `/status` | Full portfolio + bot health snapshot |
| `/stats` | **Deep performance stats** — win rate, avg win/loss, drawdown, Sharpe |
| `/positions` | List all currently open positions |
| `/backtest [N]` | Simulate strategy on last N 1-minute BTC candles (default 1500) |
| `/pause` | Pause the trading engine |
| `/resume` | Resume the trading engine |
| `/setthreshold 0.10` | Set minimum edge required to enter a trade |
| `/setsl 0.05` | Set stop-loss probability-shift threshold |
| `/settp 0.15` | Set take-profit probability-shift threshold |
| `/setpnl 5.0` | Set P&L alert threshold in USDC |

### Dashboard Inline Buttons

- **🔄 Refresh** — update the dashboard message in-place
- **⏸ Pause/Resume** — toggle trading engine
- **📊 Deep Stats** — post the full performance stats block
- **📂 Positions** — list open positions

---

## Setup

### 1. Install Python Dependencies

```bash
cd bot
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USER_ID` | Your Telegram numeric user ID |
| `POLYMARKET_ADDRESS` | `0xc7b9939135F5143D5b9eB968cf6f93566E31ff52` ← your API wallet |
| `POLYMARKET_PK` | Private key for signing orders (never the custodial wallet PK) |
| `POLYMARKET_API_KEY` | From [Polymarket API](https://docs.polymarket.com/api-reference/authentication) |
| `POLYMARKET_API_PASSPHRASE` | — |
| `POLYMARKET_API_SECRET` | — |
| `TRADING_MODE` | `DRY_RUN` (safe) or `LIVE` |
| `EDGE_THRESHOLD` | Default `0.10` (10% minimum edge) |
| `STOP_LOSS_PCT` | Default `0.05` (5% probability shift triggers SL) |
| `TAKE_PROFIT_PCT` | Default `0.15` (15% probability shift triggers TP) |
| `PNL_ALERT_THRESHOLD` | Default `5.0` USDC — alert when cumulative PnL moves by this much |
| `INITIAL_BALANCE` | Simulated starting balance for DRY_RUN performance tracking |

### 3. Run the Bot

```bash
# From project root
python -m bot.main

# Or from within the bot folder
cd bot && python main.py
```

### 4. Run a Backtest Standalone

```bash
python -m bot.backtest --limit 2000 --edge 0.10 --sl 0.05 --tp 0.15
```

---

## Strategy Formula

```
Z = (BTC_Price − Strike) / (σ × √(t/T))

P(Yes) ≈ 0.5 + Z/2        (linear CDF approximation)

Edge_YES = P(Yes) − Market_Price_YES
Edge_NO  = P(No)  − Market_Price_NO

Enter when Edge > edge_threshold
```

- **σ** = 100 USD (volatility proxy per 5-minute window)
- **t** = seconds remaining to market expiry
- **T** = 300 s (full 5-minute window)

---

## Architecture

```
main.py
├── TradingBot
│   ├── price_feed_loop()       — BTC/USDT tick from Binance
│   ├── market_discovery_loop() — Polymarket Gamma API scan
│   ├── trading_loop()
│   │   ├── _manage_positions() — SL / TP / expiry resolution
│   │   └── _scan_entries()     — Z-Score edge detection
│   ├── PerformanceTracker      — live win rate, drawdown, Sharpe
│   └── Telegram Commands       — /start /stats /backtest ...
│
backtest.py
└── Backtester                  — Binance OHLCV simulation engine
```

---

## Important Notes

- **`POLYMARKET_ADDRESS`** is your Polymarket API wallet (`0xc7b993...ff52`). Do **not** send funds here directly — this address is for API authentication only.
- Orders are only placed when `TRADING_MODE=LIVE` **and** the CLOB client initialises successfully.
- `DRY_RUN` mode fully simulates position tracking, SL/TP, PnL alerts, and stats — no funds are moved.
