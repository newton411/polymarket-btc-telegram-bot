# 🚀 RECON HFT — Polymarket BTC Trading Bot

**High-Frequency 5-Minute BTC Prediction Market Bot**

A sophisticated trading bot that exploits arbitrage opportunities and momentum in Polymarket's 5-minute Bitcoin prediction markets. Features real-time Bayesian analysis, risk management, and comprehensive Telegram control.

---

## ⚠️ IMPORTANT WARNINGS

**HIGH RISK — EDUCATIONAL ONLY**
- This bot can lose your entire trading capital
- Polymarket trading involves significant risk
- Never trade with money you cannot afford to lose
- Past performance does not guarantee future results
- Always start with DRY_RUN=true for testing

---

## ✨ Key Features

### 🤖 Advanced Trading Strategies
- **🎯 Arbitrage Detection**: Risk-free opportunities when ask_sum < target (default 0.96)
- **⚡ Last-Second Sniping**: Momentum-based entries using external BTC price feeds
- **📈 Momentum Trading**: Bayesian probability analysis with volume confirmation
- **🏦 Market Making**: Dynamic quoting when spreads are too wide

### 🛡️ Risk Management
- **DRY_RUN Mode**: Complete simulation (default enabled)
- **Position Limits**: Maximum size per trade and daily exposure
- **Stop-Loss/Take-Profit**: Automated exit rules
- **Drawdown Protection**: Emergency shutdown on excessive losses
- **Rate Limiting**: Respect API limits and avoid bans

### 📊 Real-Time Monitoring
- **Telegram Dashboard**: Live portfolio and performance updates
- **Performance Analytics**: Win rate, Sharpe ratio, drawdown metrics
- **Trade Logging**: Complete audit trail of all activities
- **Alert System**: P&L notifications and risk warnings

### 🔧 Technical Excellence
- **Multi-Provider Price Feeds**: Binance primary + Kraken fallback
- **Async Architecture**: High-performance concurrent operations
- **Error Recovery**: Automatic retries and graceful degradation
- **Modular Design**: Clean separation of concerns

---

## 🏗️ Architecture

```
bot/
├── main.py              # Entry point and orchestration
├── config.py            # Environment and constants
├── polymarket.py        # Gamma API discovery + CLOB client
├── strategies.py        # Trading strategy implementations
├── telegram_bot.py      # Telegram interface and dashboard
├── price_feed.py        # Multi-provider BTC price feeds
├── utils.py             # Logging, Decimal helpers, retries
├── .env.example         # Configuration template
└── requirements.txt     # Python dependencies
```

---

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone and enter directory
cd polymarket-btc-telegram-bot/bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required Settings:**
```bash
# Telegram (get from @BotFather)
TELEGRAM_TOKEN=7377493035:AAGj7givCiG02bio_4TnVxLxV31fuOUHzqc
ALLOWED_USER_ID=your_telegram_user_id

# Trading (start with these defaults)
DRY_RUN=true
TARGET_SUM=0.96
MAX_POSITION_SIZE=20.0
```

**Optional (for live trading):**
```bash
POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_ADDRESS=your_wallet_address
```

### 3. Launch Bot

```bash
python main.py
```

### 4. Telegram Control

1. Start a chat with your bot
2. Send `/start` to access the main menu
3. Use inline buttons or commands to control trading

---

## 📱 Telegram Commands

### Basic Commands
- `/start` — Main menu with inline controls
- `/status` — Current bot status and portfolio
- `/help` — Command reference and features

### Trading Control
- `/pause` — Pause all trading activities
- `/resume` — Resume trading operations
- `/dryrun on|off` — Toggle simulation mode

### Configuration
- `/settarget 0.96` — Set arbitrage threshold
- `/setsize 20.0` — Set maximum position size

### Monitoring
- `/stats` — Detailed performance analytics
- `/pnl` — Profit and loss summary
- `/logs` — Recent activity log

### Dashboard Buttons
- **🔄 Refresh** — Update dashboard data
- **⏸️ Pause/Resume** — Toggle trading state
- **📊 Stats** — View performance metrics
- **💰 P&L** — Check profit/loss status
- **⚙️ Settings** — Adjust bot parameters

---

## ⚙️ Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | Simulation mode (recommended) |
| `TARGET_SUM` | `0.96` | Arbitrage threshold |
| `MAX_POSITION_SIZE` | `20.0` | Max USD per trade |
| `EDGE_THRESHOLD` | `0.02` | Minimum edge to trade |
| `POLL_INTERVAL` | `3.0` | Market check frequency (seconds) |
| `DAILY_DRAWDOWN_STOP` | `0.10` | Max daily loss (10%) |

---

## 📈 Strategy Details

### Arbitrage Strategy
- Monitors order books for sum(ask_prices) < TARGET_SUM
- Places limit orders on both YES/NO sides
- Risk-free profit when spread is favorable

### Sniping Strategy
- Uses external BTC price momentum
- Bayesian probability analysis
- Last-second entries before market resolution

### Momentum Strategy
- Volume-weighted price analysis
- Trend confirmation algorithms
- Position sizing based on conviction

### Market Making
- Provides liquidity when spreads are wide
- Dynamic quoting with inventory management
- Profit from bid-ask spread

---

## 🔍 Monitoring & Logs

### Log Files
- `bot.log` — Complete activity log
- Console output — Real-time status updates

### Key Metrics
- **Win Rate**: Percentage of profitable trades
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Largest peak-to-valley decline
- **Profit Factor**: Gross profit / gross loss

### Alerts
- P&L threshold notifications
- Risk limit warnings
- System status updates
- Trade execution confirmations

---

## 🛡️ Safety Features

### Built-in Protections
- **DRY_RUN Default**: No real money at risk initially
- **Position Limits**: Maximum exposure controls
- **Rate Limiting**: API compliance and ban prevention
- **Error Recovery**: Automatic restart on failures
- **Graceful Shutdown**: Clean exit with position management

### Risk Management
- Daily drawdown limits
- Maximum trade frequency
- Exposure monitoring
- Emergency stop controls

---

## 🔧 Development

### Adding New Strategies
1. Implement strategy class in `strategies.py`
2. Add opportunity detection method
3. Register in main trading loop
4. Update Telegram interface

### Testing
```bash
# Run with dry mode
DRY_RUN=true python main.py

# Test specific components
python -c "from polymarket import PolymarketClient; print('Testing...')"
```

### Backtesting
```bash
# Run backtest via Telegram
/backtest 1000

# Or programmatically
from backtest import Backtester
bt = Backtester(limit=1000)
await bt.run()
```

---

## 📋 Requirements

- Python 3.8+
- Telegram Bot Token (from @BotFather)
- Polymarket API credentials (for live trading)
- Stable internet connection

### Dependencies
- `py-clob-client` — Polymarket CLOB API
- `python-telegram-bot` — Telegram interface
- `ccxt` — Cryptocurrency exchange API
- `tenacity` — Retry logic
- `python-dotenv` — Environment management

---

## 🚨 Legal & Compliance

- This software is for educational purposes only
- Trading cryptocurrencies involves substantial risk
- Users are responsible for compliance with local laws
- No financial advice is provided
- Use at your own risk

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly with DRY_RUN=true
4. Submit a pull request

---

## 📞 Support

- **Issues**: GitHub Issues
- **Telegram**: Direct bot commands
- **Logs**: Check `bot.log` for debugging

---

**Remember: Always start with DRY_RUN=true and small position sizes when testing live trading!**
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
