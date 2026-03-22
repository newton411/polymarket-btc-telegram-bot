# RecondTrade Bot — Polymarket BTC HFT

A production-grade Polymarket arbitrage bot for 5-minute BTC Up/Down markets, with Telegram dashboard, real-time Gamma API data, and CLOB order placement.

## Architecture

```
bot/
├── main.py              # Entry point — orchestrates all components
├── config.py            # Config & environment validation
├── polymarket_client.py # Gamma API + CLOB client (RobotTraders patterns)
├── price_feed.py        # Multi-source BTC price (Binance/Kraken/CoinGecko/CoinCap)
├── strategies.py        # Dynamic Sum Arbitrage strategy engine
├── telegram_bot.py      # Full Telegram dashboard + commands
├── backtest.py          # Historical backtesting engine
├── points_manager.py    # Points & leaderboard system
├── subscription.py      # Pro subscription management
└── utils.py             # Logging, validation helpers
```

## Polymarket API Integration

Based on [RobotTraders/bits_and_bobs](https://github.com/RobotTraders/bits_and_bobs/blob/main/polymarket_python.ipynb):

| API | Purpose | Auth |
|-----|---------|------|
| `gamma-api.polymarket.com/markets` | Market discovery, prices | None |
| `clob.polymarket.com/book` | Real-time order book | None |
| `clob.polymarket.com` + py-clob-client | Order placement | Private key |
| `data-api.polymarket.com/positions` | User positions | None |

### Key Pattern (from RobotTraders notebook)

```python
from py_clob_client.client import ClobClient

# Read-only (no auth)
client = ClobClient("https://clob.polymarket.com")
book   = client.get_order_book(yes_token_id)
mid    = client.get_midpoint(yes_token_id)   # {"mid": "0.62"}
spread = client.get_spread(yes_token_id)     # {"spread": "0.02"}

# Authenticated (for orders)
auth_client = ClobClient(CLOB_API, key=PK, chain_id=137, funder=ADDRESS)
creds = auth_client.derive_api_key()
auth_client.set_api_creds(creds)

# Get clobTokenIds from Gamma API (JSON string field)
import json
token_ids = json.loads(market['clobTokenIds'])
yes_token_id = token_ids[0]
no_token_id  = token_ids[1]
```

## Setup

### 1. Install dependencies

```bash
cd bot
pip install -r requirements.txt

# Install py-clob-client (not on standard PyPI)
pip install py-clob-client
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

**Required for DRY_RUN (read-only):**
- `TELEGRAM_TOKEN` — from @BotFather
- `ALLOWED_USER_ID` — your Telegram user ID from @userinfobot

**Required for LIVE trading:**
- `POLYMARKET_PRIVATE_KEY` — your Polygon wallet private key
- `POLYMARKET_ADDRESS` — your wallet address (`0xc7b9...`)

### 3. Run

```bash
cd bot
python main.py
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/status` | Bot status & recent opportunities |
| `/markets` | **Live** BTC 5-min markets from Gamma API |
| `/price` | Real-time BTC price (4 sources) |
| `/scan` | Scan for arbitrage opportunities |
| `/book <token_id>` | CLOB order book for any token |
| `/points` | Your points & Pro status |
| `/leaderboard` | Top 10 users |
| `/stats` | Performance stats |
| `/pause` | Pause trading |
| `/resume` | Resume trading |
| `/dryrun on\|off` | Toggle dry-run mode |
| `/settarget <0.xx>` | Set arbitrage target sum |
| `/setsize <N>` | Set trade size |
| `/pnl` | Today's P&L |
| `/backtest` | Run historical backtest |

## Strategy

**Dynamic Sum Arbitrage**: Buy both YES and NO when `YES_price + NO_price < target_sum`

```
Edge  = (1 - sum) / 2
Profit = position_size × edge (per leg)
```

This is mathematically guaranteed profit when both legs resolve.

## Risk Warning

**HIGH RISK**: Prediction market trading can result in total loss of capital. Always start with `DRY_RUN=true` and only use capital you can afford to lose.

## Wallet

Creator wallet (Polygon): `0x74299c15CcEf4b48B06633E44F4F131209E0d233`
