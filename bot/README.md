# RecondTrade Bot

**Production-ready Polymarket BTC arbitrage bot with Telegram dashboard, points system, and Pro subscriptions.**

---

## What It Does

- Scans Polymarket's 5-minute BTC Up/Down markets every **2 seconds**
- Triggers when `YES_ask + NO_ask ≤ 0.95` (configurable)
- Buys **25 shares on both legs** simultaneously (Dynamic Sum Arbitrage)
- Maintains a live **Telegram dashboard** (auto-updated every 15s)
- Awards **$RCDT points** for every detected opportunity
- Supports **Pro subscriptions** via Polygon MATIC payment
- **Dry-run mode ON by default** — no real money at risk until you're ready

---

## Quick Start (Termux on Android)

```bash
# 1. Install Termux from F-Droid (not Play Store)

# 2. Update packages
pkg update && pkg upgrade -y

# 3. Install Python and git
pkg install python git -y

# 4. Clone the repo
git clone https://github.com/newton411/polymarket-btc-telegram-bot.git
cd polymarket-btc-telegram-bot/bot

# 5. Install Python dependencies
pip install python-telegram-bot aiohttp python-dotenv

# 6. (Optional) Install py-clob-client for LIVE order placement
pip install py-clob-client

# 7. Copy and edit your .env file
cp .env.example .env
nano .env    # or: vim .env

# 8. Run the bot
python bot.py
```

---

## Required .env Values

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | ✅ | From @BotFather |
| `ALLOWED_USER_ID` | ✅ | Your Telegram user ID (from @userinfobot) |
| `POLYMARKET_ADDRESS` | ✅ (for Pro payments) | Polygon wallet for subscriptions |
| `POLYMARKET_PRIVATE_KEY` | Live only | Polygon wallet private key |
| `DRY_RUN` | — | `true` (default) or `false` |

---

## Commands

### General
| Command | Description |
|---|---|
| `/start` | Launch bot, pin dashboard, earn 100 welcome points |
| `/status` | Snapshot of the live dashboard |
| `/stats` | Your personal trade stats and points |
| `/points` | Points balance and multiplier |
| `/leaderboard` | Top 10 traders by points |
| `/referral` | Your referral link (earn 250 pts per friend) |
| `/pnl` | P&L summary |
| `/tge` | Token Generation Event info |

### Subscription
| Command | Description |
|---|---|
| `/subscribe` | Show Pro payment wallet and instructions |
| `/verify <txhash>` | Submit your Polygon tx to activate Pro |

### Owner-Only (ALLOWED_USER_ID)
| Command | Description |
|---|---|
| `/pause` | Pause the trading engine |
| `/resume` | Resume trading |
| `/dryrun on\|off` | Toggle dry-run mode |
| `/settarget 0.95` | Change the arb target sum |
| `/setsize 25` | Change shares per leg |
| `/scan` | Manual one-shot market scan |
| `/markets` | List active BTC 5-min markets |
| `/logs` | Show last 20 log lines |

---

## Trading Strategy: Dynamic Sum Arbitrage

```
When YES_ask + NO_ask ≤ TARGET_SUM:

  BUY SIZE shares of YES at YES_ask  (GTC, post-only)
  BUY SIZE shares of NO  at NO_ask   (GTC, post-only)

  Cost   = sum * SIZE   (e.g. 0.94 × 25 = $23.50)
  Payout = 1.00 * SIZE  (one leg always wins  = $25.00)
  Edge   = (1 - sum) * SIZE  = $1.50
```

The strategy is **market-neutral** — it doesn't matter whether BTC goes up or down.

---

## Points System

| Action | Points |
|---|---|
| First `/start` | +100 |
| Each trade detected | +10 (×2 with Pro) |
| Refer a friend | +250 |
| New user from referral | +50 |
| Activate Pro | +500 |
| Visit `/tge` | +25 |

---

## Pro Subscription

1. Run `/subscribe` → bot shows the creator wallet address
2. Send **5 MATIC** on Polygon to that address
3. Copy the transaction hash
4. Run `/verify <txhash>` → bot verifies on Polygonscan and activates Pro

**Pro benefits:** ×2 points multiplier · Priority alerts · TGE allocation · 30-day validity

---

## File Structure

```
bot/
├── bot.py          ← SINGLE-FILE production bot (run this)
├── .env.example    ← Copy to .env
├── tge.html        ← TGE landing page (auto-generated)
├── points.db       ← SQLite database (auto-created)
├── bot.log         ← Log file (auto-created)
│
│   (Legacy multi-file bot — kept for reference)
├── main.py
├── config.py
├── polymarket_client.py
├── strategies.py
├── telegram_bot.py
├── price_feed.py
├── points_manager.py
├── subscription.py
└── utils.py
```

---

## Safety Notes

- **Never share your private key.** It's only used locally to sign orders.
- Keep `DRY_RUN=true` until you've verified the bot is working correctly.
- Set a realistic `DAILY_DRAWDOWN_STOP` (default 10%) to limit losses.
- Polymarket requires KYC-free participation but check your local regulations.

---

## License

MIT — use at your own risk. This is not financial advice.

Creator wallet: `0x74299c15CcEf4b48B06633E44F4F131209E0d233`
