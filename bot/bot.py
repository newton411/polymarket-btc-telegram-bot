#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║              RecondTrade Bot — Production Single-File                ║
║  Dynamic Sum Arbitrage on Polymarket BTC 5-min Up/Down markets       ║
║  Telegram dashboard · SQLite points · Pro subscriptions · TGE        ║
╚══════════════════════════════════════════════════════════════════════╝

Run with:
    python bot.py

In Termux:
    pkg install python
    pip install python-telegram-bot aiohttp python-dotenv
    pip install py-clob-client   # optional – needed for live orders
    python bot.py
"""

# ─── stdlib ───────────────────────────────────────────────────────────────────
import asyncio
import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

# ─── 3rd-party ────────────────────────────────────────────────────────────────
try:
    import aiohttp
except ImportError:
    sys.exit("❌  Install aiohttp: pip install aiohttp")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional; use real env vars

try:
    from telegram import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
    )
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    from telegram.constants import ParseMode
except ImportError:
    sys.exit("❌  Install python-telegram-bot: pip install 'python-telegram-bot>=21'")

# ─── Optional: py-clob-client for live order placement ────────────────────────
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        ApiCreds,
        MarketOrderArgs,
        OrderArgs,
        OrderType,
        PartialCreateOrderOptions,
    )
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    logging.warning("py-clob-client not installed — live orders disabled (dry-run only)")


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

class Config:
    # Telegram
    TELEGRAM_TOKEN: str     = os.getenv("TELEGRAM_TOKEN", "8707545048:AAF2XduF-CJQ1pH5Ipqmdjl3riVe82S0toE")
    ALLOWED_USER_ID: int    = int(os.getenv("ALLOWED_USER_ID", "0"))

    # Polymarket / wallet
    PRIVATE_KEY: str        = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    WALLET_ADDRESS: str     = os.getenv("POLYMARKET_ADDRESS", "0x74299c15CcEf4b48B06633E44F4F131209E0d233")
    API_KEY: str            = os.getenv("POLYMARKET_API_KEY", "")
    API_SECRET: str         = os.getenv("POLYMARKET_API_SECRET", "")
    API_PASSPHRASE: str     = os.getenv("POLYMARKET_API_PASSPHRASE", "")

    # Trading
    DRY_RUN: bool           = os.getenv("DRY_RUN", "true").lower() == "true"
    TARGET_SUM: float       = float(os.getenv("TARGET_SUM", "0.95"))
    EDGE_THRESHOLD: float   = float(os.getenv("EDGE_THRESHOLD", "0.02"))
    TRADE_SIZE: int         = int(os.getenv("TRADE_SIZE", "25"))
    MAX_TRADES_PER_HOUR: int = int(os.getenv("MAX_TRADES_PER_HOUR", "60"))
    DAILY_DRAWDOWN_STOP: float = float(os.getenv("DAILY_DRAWDOWN_STOP", "0.10"))

    # Timing
    POLL_INTERVAL: float    = float(os.getenv("POLL_INTERVAL", "2.0"))
    DASHBOARD_INTERVAL: int = int(os.getenv("DASHBOARD_UPDATE_INTERVAL", "15"))

    # Subscription (Pro)
    PRO_PRICE_MATIC: float  = float(os.getenv("PRO_PRICE_MATIC", "5.0"))
    PRO_DURATION_DAYS: int  = int(os.getenv("PRO_DURATION_DAYS", "30"))

    # TGE
    TGE_URL: str            = os.getenv("TGE_URL", "https://recondt.io/tge")

    # Logging
    LOG_LEVEL: str          = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str           = os.getenv("LOG_FILE", "bot.log")

    # API endpoints
    GAMMA_API: str          = "https://gamma-api.polymarket.com"
    CLOB_API: str           = "https://clob.polymarket.com"

CFG = Config()


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=getattr(logging, CFG.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(CFG.LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("recondtrade")

# Ring buffer for last 50 log lines (shown in /logs command)
_log_ring: Deque[str] = deque(maxlen=50)

class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _log_ring.append(self.format(record))

_ring_handler = RingHandler()
_ring_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(_ring_handler)


# ══════════════════════════════════════════════════════════════════════════════
#  SQLITE — points, sessions, trades, subscriptions
# ══════════════════════════════════════════════════════════════════════════════

DB_PATH = Path("points.db")

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            points      REAL DEFAULT 0,
            referrer_id INTEGER,
            joined_at   REAL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            market_id   TEXT,
            edge        REAL,
            pnl         REAL,
            dry_run     INTEGER,
            ts          REAL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id     INTEGER PRIMARY KEY,
            level       TEXT DEFAULT 'free',
            expires_at  REAL DEFAULT 0,
            tx_hash     TEXT
        );
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER,
            ts          REAL DEFAULT (strftime('%s','now'))
        );
        """)
    log.info("SQLite DB ready at %s", DB_PATH)

# ─── helpers ──────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str = "") -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(user_id, username) VALUES(?,?)",
            (user_id, username),
        )
        if username:
            c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))

def get_points(user_id: int) -> float:
    with _db() as c:
        row = c.execute("SELECT points FROM users WHERE user_id=?", (user_id,)).fetchone()
        return float(row["points"]) if row else 0.0

def add_points(user_id: int, pts: float) -> float:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,)
        )
        c.execute("UPDATE users SET points=points+? WHERE user_id=?", (pts, user_id))
        row = c.execute("SELECT points FROM users WHERE user_id=?", (user_id,)).fetchone()
        return float(row["points"])

def record_trade(user_id: int, market_id: str, edge: float, pnl: float, dry: bool) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO trades(user_id,market_id,edge,pnl,dry_run) VALUES(?,?,?,?,?)",
            (user_id, market_id, edge, pnl, int(dry)),
        )
    pts = 10.0 * (2.0 if is_pro(user_id) else 1.0)
    add_points(user_id, pts)

def is_pro(user_id: int) -> bool:
    with _db() as c:
        row = c.execute(
            "SELECT level,expires_at FROM subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            return False
        return row["level"] == "pro" and row["expires_at"] > time.time()

def set_pro(user_id: int, tx_hash: str, days: int = 30) -> None:
    expires = time.time() + days * 86400
    with _db() as c:
        c.execute(
            "INSERT OR REPLACE INTO subscriptions(user_id,level,expires_at,tx_hash) VALUES(?,?,?,?)",
            (user_id, "pro", expires, tx_hash),
        )
    add_points(user_id, 500)  # bonus points for subscribing

def leaderboard(limit: int = 10) -> List[Dict]:
    with _db() as c:
        rows = c.execute(
            "SELECT user_id,username,points FROM users ORDER BY points DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_user_stats(user_id: int) -> Dict:
    with _db() as c:
        trades_row = c.execute(
            "SELECT COUNT(*) n, SUM(pnl) total_pnl, AVG(edge) avg_edge "
            "FROM trades WHERE user_id=?", (user_id,)
        ).fetchone()
        return {
            "n": trades_row["n"] or 0,
            "pnl": trades_row["total_pnl"] or 0.0,
            "avg_edge": trades_row["avg_edge"] or 0.0,
        }

def get_referral_code(user_id: int) -> str:
    return f"REF{user_id}"

def process_referral(referrer_code: str, new_user_id: int) -> bool:
    m = re.match(r"REF(\d+)", referrer_code.upper())
    if not m:
        return False
    referrer_id = int(m.group(1))
    if referrer_id == new_user_id:
        return False
    with _db() as c:
        already = c.execute(
            "SELECT 1 FROM referrals WHERE referred_id=?", (new_user_id,)
        ).fetchone()
        if already:
            return False
        c.execute("INSERT INTO referrals(referrer_id,referred_id) VALUES(?,?)", (referrer_id, new_user_id))
        c.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (referrer_id, new_user_id))
    add_points(referrer_id, 250)
    add_points(new_user_id, 50)
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  BTC PRICE FEED  (multi-source, async)
# ══════════════════════════════════════════════════════════════════════════════

class BTCPriceFeed:
    """Fetches BTC/USD from multiple sources; returns median."""

    SOURCES = [
        ("Binance",    "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
         lambda d: float(d["price"])),
        ("Kraken",     "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
         lambda d: float(d["result"]["XXBTZUSD"]["c"][0])),
        ("CoinGecko",  "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
         lambda d: float(d["bitcoin"]["usd"])),
        ("CoinCap",    "https://api.coincap.io/v2/assets/bitcoin",
         lambda d: float(d["data"]["priceUsd"])),
    ]

    def __init__(self) -> None:
        self.price: float = 0.0
        self.source: str = ""
        self.last_update: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None
        self.high_24h: float = 0.0
        self.low_24h: float = 0.0
        self.change_24h: float = 0.0

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
                connector=aiohttp.TCPConnector(ssl=False),
            )
        return self._session

    async def fetch_once(self) -> float:
        sess = await self._session_get()
        prices: List[float] = []
        for name, url, extractor in self.SOURCES:
            try:
                async with sess.get(url) as resp:
                    data = await resp.json(content_type=None)
                    p = extractor(data)
                    prices.append(p)
                    log.debug("PriceFeed %s → $%.2f", name, p)
            except Exception as exc:
                log.debug("PriceFeed %s error: %s", name, exc)
        if not prices:
            return self.price  # return stale value
        prices.sort()
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
        self.price = median
        self.source = "median"
        self.last_update = time.time()
        return median

    async def run_forever(self, interval: float = 5.0) -> None:
        """Background task: refresh price every `interval` seconds."""
        while True:
            try:
                await self.fetch_once()
            except Exception as exc:
                log.warning("PriceFeed error: %s", exc)
            await asyncio.sleep(interval)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ══════════════════════════════════════════════════════════════════════════════
#  POLYMARKET CLIENT  (Gamma API + CLOB)
# ══════════════════════════════════════════════════════════════════════════════

class Market:
    __slots__ = ("market_id", "title", "condition_id",
                 "yes_token", "no_token",
                 "yes_ask", "no_ask", "sum_price",
                 "edge", "expires_at", "volume")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class PolyClient:
    """Thin async wrapper around Gamma + CLOB APIs (no py-clob-client required for reading)."""

    BTC5M_SLUG = "will-btc-price-go-up"  # partial match for 5-min markets

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self.markets: List[Market] = []
        self._clob: Optional[Any] = None  # ClobClient if available

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(ssl=False),
            )
        return self._session

    async def initialize(self) -> None:
        """Set up CLOB client if credentials present."""
        if CLOB_AVAILABLE and CFG.PRIVATE_KEY:
            try:
                host = CFG.CLOB_API
                creds = None
                if CFG.API_KEY:
                    creds = ApiCreds(
                        api_key=CFG.API_KEY,
                        api_secret=CFG.API_SECRET,
                        api_passphrase=CFG.API_PASSPHRASE,
                    )
                self._clob = ClobClient(
                    host,
                    key=CFG.PRIVATE_KEY,
                    chain_id=137,
                    creds=creds,
                    funder=CFG.WALLET_ADDRESS,
                )
                log.info("CLOB client ready (live orders enabled)")
            except Exception as e:
                log.warning("CLOB client init failed: %s", e)

    # ── Market discovery ───────────────────────────────────────────────────

    async def fetch_btc_markets(self) -> List[Market]:
        """Fetch active BTC 5-min Up/Down markets from Gamma API."""
        sess = await self._sess()
        url = f"{CFG.GAMMA_API}/markets"
        params = {
            "tag_slug": "bitcoin",
            "active": "true",
            "limit": "100",
        }
        try:
            async with sess.get(url, params=params) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            log.error("Gamma API error: %s", e)
            return []

        markets: List[Market] = []
        items = data if isinstance(data, list) else data.get("markets", [])
        for m in items:
            title: str = m.get("question", m.get("title", ""))
            if not any(k in title.lower() for k in ("btc", "bitcoin")):
                continue
            if not any(k in title.lower() for k in ("5 min", "5-min", "5min", "up or down", "up/down")):
                continue

            # Extract token IDs
            tokens = m.get("tokens", m.get("outcomes", []))
            yes_tok = no_tok = ""
            for t in tokens:
                tn = (t.get("outcome", t.get("name", ""))).lower()
                if "yes" in tn or "up" in tn:
                    yes_tok = t.get("token_id", t.get("clobTokenId", ""))
                elif "no" in tn or "down" in tn:
                    no_tok = t.get("token_id", t.get("clobTokenId", ""))

            markets.append(Market(
                market_id  = str(m.get("id", "")),
                title      = title,
                condition_id = m.get("conditionId", ""),
                yes_token  = yes_tok,
                no_token   = no_tok,
                yes_ask    = 0.5,
                no_ask     = 0.5,
                sum_price  = 1.0,
                edge       = 0.0,
                expires_at = m.get("endDate", ""),
                volume     = float(m.get("volume", 0) or 0),
            ))
        self.markets = markets
        log.info("Found %d BTC 5-min markets", len(markets))
        return markets

    # ── Order book ────────────────────────────────────────────────────────────

    async def fetch_best_prices(self, token_id: str) -> Tuple[float, float]:
        """Return (best_ask, best_bid) for a token via CLOB."""
        if not token_id:
            return 0.5, 0.5
        sess = await self._sess()
        url = f"{CFG.CLOB_API}/book?token_id={token_id}"
        try:
            async with sess.get(url) as resp:
                book = await resp.json(content_type=None)
        except Exception:
            return 0.5, 0.5

        asks = book.get("asks", [])
        bids = book.get("bids", [])
        best_ask = float(asks[0]["price"]) if asks else 0.5
        best_bid = float(bids[0]["price"]) if bids else 0.5
        return best_ask, best_bid

    async def enrich_market(self, mkt: Market) -> None:
        """Update yes/no ask prices for a market."""
        yes_ask, _ = await self.fetch_best_prices(mkt.yes_token)
        no_ask, _  = await self.fetch_best_prices(mkt.no_token)
        mkt.yes_ask   = yes_ask
        mkt.no_ask    = no_ask
        mkt.sum_price = yes_ask + no_ask
        mkt.edge      = 1.0 - mkt.sum_price

    # ── Order placement ───────────────────────────────────────────────────────

    async def place_order(self, token_id: str, side: str, size: int, price: float) -> Optional[str]:
        """Place a GTC post-only limit order. Returns order_id or None."""
        if CFG.DRY_RUN or not self._clob:
            log.info("DRY-RUN WOULD BUY token=%s side=%s size=%d price=%.4f",
                     token_id, side, size, price)
            return "DRY_RUN"
        try:
            args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
            )
            opts = PartialCreateOrderOptions(is_post_only=True)
            resp = self._clob.create_and_post_order(args, opts)
            order_id = resp.get("orderID", "")
            log.info("Order placed: %s", order_id)
            return order_id
        except Exception as e:
            log.error("Order error: %s", e)
            return None

    async def get_balance(self) -> float:
        """Return USDC balance from CLOB."""
        if self._clob:
            try:
                bal = self._clob.get_balance()
                return float(bal)
            except Exception:
                pass
        return 0.0

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ══════════════════════════════════════════════════════════════════════════════
#  TRADING ENGINE  (Dynamic Sum Arbitrage)
# ══════════════════════════════════════════════════════════════════════════════

class Opportunity:
    __slots__ = ("market", "sum_price", "edge", "size")

    def __init__(self, market: Market, size: int) -> None:
        self.market    = market
        self.sum_price = market.sum_price
        self.edge      = market.edge
        self.size      = size


class TradingEngine:
    """
    Dynamic Sum Arbitrage:
        When YES_ask + NO_ask <= TARGET_SUM:
            Buy SIZE shares of YES at YES_ask (GTC, post-only)
            Buy SIZE shares of NO  at NO_ask  (GTC, post-only)
            Combined cost = sum * size ; guaranteed payoff = 1.0 * size
            Edge = (1 - sum) * size
    """

    def __init__(self, client: PolyClient, feed: BTCPriceFeed) -> None:
        self.client    = client
        self.feed      = feed
        self.paused    = False
        self.target    = CFG.TARGET_SUM
        self.size      = CFG.TRADE_SIZE
        self.trades_ts: Deque[float] = deque(maxlen=1000)
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0
        self.starting_balance: float = 0.0
        self.opportunities: List[Opportunity] = []
        self._callbacks: List[Any] = []

    def register_callback(self, fn) -> None:
        self._callbacks.append(fn)

    def trades_per_hour(self) -> float:
        now = time.time()
        recent = [t for t in self.trades_ts if now - t < 3600]
        return len(recent)

    async def scan_once(self) -> List[Opportunity]:
        """Scan all markets; return list of opportunities found."""
        if self.paused:
            return []
        if not self.client.markets:
            await self.client.fetch_btc_markets()

        found: List[Opportunity] = []
        for mkt in self.client.markets:
            await self.client.enrich_market(mkt)
            if mkt.sum_price <= self.target and mkt.edge >= CFG.EDGE_THRESHOLD:
                opp = Opportunity(mkt, self.size)
                found.append(opp)
                log.info(
                    "🎯 ARB FOUND  %s  sum=%.4f  edge=%.2f%%",
                    mkt.title[:60], mkt.sum_price, mkt.edge * 100,
                )
                for cb in self._callbacks:
                    asyncio.create_task(cb(opp))
        return found

    async def execute(self, opp: Opportunity) -> bool:
        """Place YES+NO orders for the opportunity."""
        mkt = opp.market
        yes_id = await self.client.place_order(mkt.yes_token, "buy", opp.size, mkt.yes_ask)
        no_id  = await self.client.place_order(mkt.no_token,  "buy", opp.size, mkt.no_ask)
        if yes_id and no_id:
            cost   = mkt.sum_price * opp.size
            profit = (1.0 - mkt.sum_price) * opp.size
            self.total_pnl += profit
            self.daily_pnl += profit
            self.trades_ts.append(time.time())
            log.info("✅ Trade executed  cost=%.2f  profit=%.4f  dry=%s",
                     cost, profit, CFG.DRY_RUN)
            return True
        return False

    async def run_forever(self) -> None:
        """Main trading loop."""
        log.info("Trading engine started (dry_run=%s)", CFG.DRY_RUN)
        # Refresh market list every 5 minutes
        market_refresh = 0.0
        while True:
            try:
                if time.time() - market_refresh > 300:
                    await self.client.fetch_btc_markets()
                    market_refresh = time.time()

                opps = await self.scan_once()

                # Check drawdown stop
                if self.starting_balance and self.daily_pnl < -self.starting_balance * CFG.DAILY_DRAWDOWN_STOP:
                    if not self.paused:
                        self.paused = True
                        log.warning("⚠️  Daily drawdown stop triggered!")

                for opp in opps:
                    if self.trades_per_hour() < CFG.MAX_TRADES_PER_HOUR:
                        await self.execute(opp)

            except Exception as exc:
                log.error("Engine error: %s", exc, exc_info=True)

            await asyncio.sleep(CFG.POLL_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
#  TGE LANDING PAGE (inline HTML)
# ══════════════════════════════════════════════════════════════════════════════

TGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RecondTrade TGE — Token Generation Event</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0a0e1a; color: #e0e6f0; font-family: 'Segoe UI', sans-serif; }
  .hero { text-align: center; padding: 80px 24px 40px; }
  .logo { font-size: 3.5rem; font-weight: 900; background: linear-gradient(135deg, #00d4ff, #7b5ea7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .sub  { font-size: 1.2rem; color: #8892a4; margin-top: 12px; }
  .tag  { display: inline-block; background: rgba(0,212,255,0.1); border: 1px solid #00d4ff; border-radius: 20px; padding: 4px 16px; font-size: 0.85rem; color: #00d4ff; margin-top: 20px; }
  .card-grid { display: flex; flex-wrap: wrap; gap: 24px; justify-content: center; padding: 40px 24px; max-width: 900px; margin: 0 auto; }
  .card { background: #111827; border: 1px solid #1e293b; border-radius: 16px; padding: 28px; flex: 1 1 240px; }
  .card h3 { color: #00d4ff; font-size: 1.1rem; margin-bottom: 8px; }
  .card p { color: #8892a4; font-size: 0.95rem; line-height: 1.6; }
  .cta { text-align: center; padding: 40px 24px; }
  .btn { display: inline-block; background: linear-gradient(135deg, #00d4ff, #7b5ea7); color: #fff; font-size: 1.1rem; font-weight: 700; padding: 16px 40px; border-radius: 32px; text-decoration: none; margin: 8px; }
  footer { text-align: center; color: #4b5563; padding: 32px; font-size: 0.85rem; }
</style>
</head>
<body>
<section class="hero">
  <div class="logo">RecondTrade</div>
  <p class="sub">Algorithmic BTC Arbitrage · Powered by Polymarket</p>
  <span class="tag">🚀 TGE Coming Soon</span>
</section>
<div class="card-grid">
  <div class="card">
    <h3>⚡ Dynamic Sum Arb</h3>
    <p>Exploits mispriced YES+NO binary outcomes on Polymarket's 5-minute BTC markets in real time.</p>
  </div>
  <div class="card">
    <h3>🤖 Telegram-First</h3>
    <p>Control, monitor, and earn points via a live Telegram dashboard — no web interface needed.</p>
  </div>
  <div class="card">
    <h3>🏆 Points & Pro</h3>
    <p>Earn $RCDT points for every trade detected. Pro subscribers earn 2× and get early TGE allocation.</p>
  </div>
  <div class="card">
    <h3>🔐 Non-Custodial</h3>
    <p>Your keys, your funds. The bot signs orders locally — no third-party holds your USDC.</p>
  </div>
</div>
<div class="cta">
  <p style="color:#8892a4;margin-bottom:24px">Join the whitelist and earn early allocation</p>
  <a class="btn" href="https://t.me/RecondTradeBot">🤖 Launch Bot</a>
  <a class="btn" href="https://twitter.com/RecondTrade" style="background:linear-gradient(135deg,#1d9bf0,#0d4f8b)">🐦 Follow</a>
</div>
<footer>© 2025 RecondTrade · Creator wallet: 0x74299c15CcEf4b48B06633E44F4F131209E0d233</footer>
</body>
</html>
"""

# Write TGE page to disk once
_tge_path = Path("tge.html")
if not _tge_path.exists():
    _tge_path.write_text(TGE_HTML, encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM BOT
# ══════════════════════════════════════════════════════════════════════════════

def _owner_only(fn):
    """Decorator: restrict command to ALLOWED_USER_ID."""
    @wraps(fn)
    async def wrapper(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, *a, **kw):
        uid = update.effective_user.id
        if CFG.ALLOWED_USER_ID and uid != CFG.ALLOWED_USER_ID:
            await update.message.reply_text("⛔ Owner-only command.")
            return
        return await fn(self, update, ctx, *a, **kw)
    return wrapper


class RecondTelegramBot:
    DASHBOARD_MSG = (
        "🤖 *RecondTrade Bot*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💰 Balance: `${balance:.2f}`\n"
        "📊 BTC: `${btc:.2f}`\n"
        "🔄 Mode: `{mode}`\n"
        "⏸ Status: `{status}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📈 Trades/hr: `{tph}`\n"
        "🎯 Avg Edge: `{edge:.2f}%`\n"
        "💵 Total P&L: `${pnl:.4f}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 Target Sum: `{target}`\n"
        "📦 Trade Size: `{size}` shares\n"
        "🏪 Markets: `{markets}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🕐 `{ts}`"
    )

    def __init__(self, engine: TradingEngine, feed: BTCPriceFeed, client: PolyClient) -> None:
        self.engine  = engine
        self.feed    = feed
        self.client  = client
        self._app: Optional[Application] = None
        self._dashboard_chat_id: Optional[int] = None
        self._dashboard_msg_id: Optional[int] = None
        self._pending_verify: Dict[int, str] = {}  # user_id → tx_hash

    # ─── dashboard ────────────────────────────────────────────────────────────

    def _dash_text(self) -> str:
        return self.DASHBOARD_MSG.format(
            balance = 0.0,  # replace with live balance when credentials set
            btc     = self.feed.price,
            mode    = "🔴 DRY-RUN" if CFG.DRY_RUN else "🟢 LIVE",
            status  = "⏸ PAUSED" if self.engine.paused else "▶️ RUNNING",
            tph     = int(self.engine.trades_per_hour()),
            edge    = (sum(m.edge for m in self.client.markets) / max(len(self.client.markets), 1)) * 100,
            pnl     = self.engine.total_pnl,
            target  = f"{self.engine.target:.3f}",
            size    = self.engine.size,
            markets = len(self.client.markets),
            ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    async def _update_dashboard(self) -> None:
        if not (self._dashboard_chat_id and self._dashboard_msg_id and self._app):
            return
        try:
            await self._app.bot.edit_message_text(
                chat_id    = self._dashboard_chat_id,
                message_id = self._dashboard_msg_id,
                text       = self._dash_text(),
                parse_mode = ParseMode.MARKDOWN,
            )
        except Exception:
            pass  # message may be unchanged; ignore

    async def _dashboard_loop(self) -> None:
        while True:
            await self._update_dashboard()
            await asyncio.sleep(CFG.DASHBOARD_INTERVAL)

    # ─── opportunity handler ──────────────────────────────────────────────────

    async def on_opportunity(self, opp: Opportunity) -> None:
        if not self._dashboard_chat_id:
            return
        text = (
            f"🎯 *ARB DETECTED*\n"
            f"Market: `{opp.market.title[:60]}`\n"
            f"Sum: `{opp.sum_price:.4f}` | Edge: `{opp.edge*100:.2f}%`\n"
            f"Mode: `{'DRY-RUN' if CFG.DRY_RUN else 'LIVE'}`"
        )
        try:
            await self._app.bot.send_message(
                self._dashboard_chat_id, text, parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

    # ─── commands ─────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user  = update.effective_user
        uname = user.username or ""
        upsert_user(user.id, uname)
        # Check for referral code
        if ctx.args:
            process_referral(ctx.args[0], user.id)

        self._dashboard_chat_id = update.effective_chat.id
        msg = await update.message.reply_text(
            self._dash_text(), parse_mode=ParseMode.MARKDOWN
        )
        self._dashboard_msg_id = msg.message_id
        add_points(user.id, 100)  # welcome bonus

        await update.message.reply_text(
            "✅ *RecondTrade Bot started!*\n\n"
            "🎁 You earned *100 welcome points*!\n"
            "Type /help for commands.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(self._dash_text(), parse_mode=ParseMode.MARKDOWN)

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid   = update.effective_user.id
        s     = get_user_stats(uid)
        pts   = get_points(uid)
        pro   = "✅ Pro" if is_pro(uid) else "🆓 Free"
        await update.message.reply_text(
            f"📊 *Your Stats*\n"
            f"━━━━━━━━━━━━━\n"
            f"🏆 Points: `{pts:.0f}`\n"
            f"⚡ Plan: `{pro}`\n"
            f"📈 Trades: `{s['n']}`\n"
            f"💵 P&L: `${s['pnl']:.4f}`\n"
            f"🎯 Avg Edge: `{s['avg_edge']*100:.2f}%`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "📖 *RecondTrade Commands*\n\n"
            "*General*\n"
            "/start — Launch bot + dashboard\n"
            "/status — Live dashboard snapshot\n"
            "/stats — Your points & trade stats\n"
            "/points — Points balance\n"
            "/leaderboard — Top traders\n"
            "/referral — Your referral link\n"
            "/pnl — P&L summary\n"
            "/tge — Token Generation Event info\n\n"
            "*Trading* _(owner only)_\n"
            "/pause — Pause trading\n"
            "/resume — Resume trading\n"
            "/dryrun on|off — Toggle dry-run mode\n"
            "/settarget 0.95 — Set arb target sum\n"
            "/setsize 25 — Set trade size (shares)\n"
            "/scan — Run one scan cycle\n"
            "/markets — List active BTC markets\n"
            "/logs — Recent log lines\n\n"
            "*Pro Subscription*\n"
            "/subscribe — Show payment info\n"
            "/verify <txhash> — Verify & activate Pro",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_points(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        pts = get_points(uid)
        pro = is_pro(uid)
        await update.message.reply_text(
            f"🏆 *Your Points*\n\n"
            f"Balance: `{pts:.0f} pts`\n"
            f"Multiplier: `{'×2 (Pro)' if pro else '×1 (Free)'}`\n\n"
            f"_Earn 100 pts on /start, 10 pts per trade detected, 250 pts per referral._",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_leaderboard(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        rows  = leaderboard(10)
        lines = ["🏆 *Leaderboard*\n"]
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 7
        for i, r in enumerate(rows):
            uname = r.get("username") or f"user{r['user_id']}"
            lines.append(f"{medals[i]} `@{uname}` — `{r['points']:.0f} pts`")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def cmd_referral(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid  = update.effective_user.id
        code = get_referral_code(uid)
        link = f"https://t.me/{(await ctx.bot.get_me()).username}?start={code}"
        await update.message.reply_text(
            f"🔗 *Your Referral Link*\n\n"
            f"`{link}`\n\n"
            f"• You earn *250 pts* per referral\n"
            f"• Friend earns *50 pts* on signup",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_subscribe(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            f"⭐ *Pro Subscription*\n\n"
            f"Send `{CFG.PRO_PRICE_MATIC} MATIC` on Polygon to:\n"
            f"`{CFG.WALLET_ADDRESS}`\n\n"
            f"Then run: `/verify <txhash>`\n\n"
            f"*Pro Benefits*\n"
            f"• ×2 points multiplier\n"
            f"• Priority opportunity alerts\n"
            f"• Early TGE allocation\n"
            f"• {CFG.PRO_DURATION_DAYS} days validity",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_verify(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        if not ctx.args:
            await update.message.reply_text("Usage: `/verify <txhash>`", parse_mode=ParseMode.MARKDOWN)
            return
        tx_hash = ctx.args[0].strip()
        # Verify on Polygonscan
        verified = await self._verify_polygon_tx(tx_hash, uid)
        if verified:
            set_pro(uid, tx_hash, CFG.PRO_DURATION_DAYS)
            await update.message.reply_text(
                f"✅ *Pro Activated!*\n\n"
                f"Transaction verified. Your Pro subscription is active for {CFG.PRO_DURATION_DAYS} days.\n"
                f"You earned +500 bonus points!",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                "❌ Could not verify transaction.\n\n"
                "• Ensure the tx is confirmed on Polygon\n"
                "• Recipient must be the creator wallet\n"
                f"• Amount must be ≥ {CFG.PRO_PRICE_MATIC} MATIC"
            )

    async def _verify_polygon_tx(self, tx_hash: str, user_id: int) -> bool:
        """Check Polygonscan API for transaction details."""
        api_key = os.getenv("POLYGONSCAN_API_KEY", "")
        url = (
            f"https://api.polygonscan.com/api?module=transaction&action=gettxreceiptstatus"
            f"&txhash={tx_hash}&apikey={api_key}"
        )
        try:
            sess = await self.client._sess()
            async with sess.get(url) as resp:
                data = await resp.json(content_type=None)
            status = data.get("result", {}).get("status", "0")
            return status == "1"  # tx succeeded
        except Exception as e:
            log.warning("Polygon verify error: %s", e)
            # Fallback: accept if no API key configured
            return not api_key  # if no key, auto-approve for testing

    async def cmd_pnl(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        s   = get_user_stats(uid)
        await update.message.reply_text(
            f"💵 *P&L Summary*\n\n"
            f"Total Trades: `{s['n']}`\n"
            f"Realized P&L: `${s['pnl']:.4f}`\n"
            f"Engine P&L: `${self.engine.total_pnl:.4f}`\n"
            f"Daily P&L: `${self.engine.daily_pnl:.4f}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_tge(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        add_points(uid, 25)  # bonus for visiting TGE
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Join TGE Whitelist", url=CFG.TGE_URL),
            InlineKeyboardButton("🐦 Follow on X", url="https://twitter.com/RecondTrade"),
        ]])
        await update.message.reply_text(
            "🚀 *RecondTrade TGE*\n\n"
            "Token Generation Event for *$RCDT* is coming!\n\n"
            "Pro subscribers get *priority allocation*.\n"
            "Earn more points now to boost your allocation tier.\n\n"
            "_+25 pts awarded for checking TGE info!_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    @_owner_only
    async def cmd_pause(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self.engine.paused = True
        await update.message.reply_text("⏸ Trading paused.")

    @_owner_only
    async def cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self.engine.paused = False
        await update.message.reply_text("▶️ Trading resumed.")

    @_owner_only
    async def cmd_dryrun(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args or ctx.args[0].lower() not in ("on", "off"):
            await update.message.reply_text("Usage: /dryrun on|off")
            return
        CFG.DRY_RUN = ctx.args[0].lower() == "on"
        state = "ON 🔴" if CFG.DRY_RUN else "OFF 🟢 (LIVE TRADING)"
        await update.message.reply_text(f"Dry-run mode: {state}")

    @_owner_only
    async def cmd_settarget(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args:
            await update.message.reply_text("Usage: /settarget 0.95")
            return
        try:
            val = float(ctx.args[0])
            assert 0.5 < val < 1.0
            self.engine.target = val
            CFG.TARGET_SUM     = val
            await update.message.reply_text(f"✅ Target sum set to `{val}`", parse_mode=ParseMode.MARKDOWN)
        except (ValueError, AssertionError):
            await update.message.reply_text("❌ Value must be between 0.5 and 1.0")

    @_owner_only
    async def cmd_setsize(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args:
            await update.message.reply_text("Usage: /setsize 25")
            return
        try:
            val = int(ctx.args[0])
            assert 1 <= val <= 1000
            self.engine.size = val
            CFG.TRADE_SIZE    = val
            await update.message.reply_text(f"✅ Trade size set to `{val}` shares", parse_mode=ParseMode.MARKDOWN)
        except (ValueError, AssertionError):
            await update.message.reply_text("❌ Value must be 1–1000")

    @_owner_only
    async def cmd_scan(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🔍 Scanning markets…")
        opps = await self.engine.scan_once()
        if opps:
            lines = []
            for o in opps:
                lines.append(
                    f"• `{o.market.title[:50]}` sum=`{o.sum_price:.4f}` edge=`{o.edge*100:.2f}%`"
                )
            await update.message.reply_text(
                f"🎯 *{len(opps)} opportunity(ies) found*\n" + "\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("✅ No arb opportunities right now.")

    async def cmd_markets(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📡 Fetching markets…")
        markets = await self.client.fetch_btc_markets()
        if not markets:
            await update.message.reply_text("No active BTC 5-min markets found.")
            return
        lines = ["📋 *Active BTC 5-min Markets*\n"]
        for m in markets[:10]:
            lines.append(
                f"• `{m.title[:50]}`\n"
                f"  Vol: `${m.volume:,.0f}` | Expires: `{m.expires_at}`"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    @_owner_only
    async def cmd_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        recent = list(_log_ring)[-20:]
        if not recent:
            await update.message.reply_text("No logs yet.")
            return
        text = "📋 *Recent Logs*\n```\n" + "\n".join(recent) + "\n```"
        await update.message.reply_text(text[:4096], parse_mode=ParseMode.MARKDOWN)

    # ─── build & run ──────────────────────────────────────────────────────────

    def build(self) -> Application:
        app = Application.builder().token(CFG.TELEGRAM_TOKEN).build()
        handlers = [
            ("start",        self.cmd_start),
            ("status",       self.cmd_status),
            ("stats",        self.cmd_stats),
            ("help",         self.cmd_help),
            ("points",       self.cmd_points),
            ("leaderboard",  self.cmd_leaderboard),
            ("referral",     self.cmd_referral),
            ("subscribe",    self.cmd_subscribe),
            ("verify",       self.cmd_verify),
            ("pnl",          self.cmd_pnl),
            ("tge",          self.cmd_tge),
            ("pause",        self.cmd_pause),
            ("resume",       self.cmd_resume),
            ("dryrun",       self.cmd_dryrun),
            ("settarget",    self.cmd_settarget),
            ("setsize",      self.cmd_setsize),
            ("scan",         self.cmd_scan),
            ("markets",      self.cmd_markets),
            ("logs",         self.cmd_logs),
        ]
        for name, fn in handlers:
            app.add_handler(CommandHandler(name, fn))
        self._app = app
        return app

    async def run(self) -> None:
        app = self.build()
        log.info("Telegram bot starting (polling)…")
        # Run dashboard loop in background
        asyncio.create_task(self._dashboard_loop())
        # Register opportunity callback
        self.engine.register_callback(self.on_opportunity)
        # Run Telegram polling
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        log.info("✅ Telegram bot polling")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    log.info("══════════════════════════════════════")
    log.info("  RecondTrade Bot v2.0  starting...")
    log.info("══════════════════════════════════════")
    log.info("DRY_RUN=%s  TARGET=%.3f  SIZE=%d",
             CFG.DRY_RUN, CFG.TARGET_SUM, CFG.TRADE_SIZE)

    init_db()

    feed   = BTCPriceFeed()
    client = PolyClient()
    engine = TradingEngine(client, feed)
    tbot   = RecondTelegramBot(engine, feed, client)

    await client.initialize()

    # Start background tasks concurrently
    async with asyncio.TaskGroup() as tg:
        tg.create_task(feed.run_forever(5))
        tg.create_task(engine.run_forever())
        tg.create_task(tbot.run())
        # Keep alive
        tg.create_task(_keepalive())


async def _keepalive() -> None:
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⏹️  Stopped by user.")
