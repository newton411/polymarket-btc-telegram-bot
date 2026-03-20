"""
RECON HFT — Polymarket 5-Min BTC Trading Bot
Strategy: Bayesian Z-Score Edge Detection
Controls: Telegram Bot Dashboard
"""
import asyncio
import os
import logging
import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
import requests

# Polymarket SDK (optional – falls back to simulation if not installed)
try:
    from clob_client.client import ClobClient
    from clob_client.clob_types import OrderArgs, ApiCredential
    from clob_client.constants import POLYGON
except ImportError:
    ClobClient = None

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

import ccxt.async_support as ccxt

# ── Setup ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
#  PRICE FEED SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
class PriceFeed:
    """Multi-provider price feed with fallbacks."""

    def __init__(self):
        self.primary_exchange = ccxt.binance({"enableRateLimit": True})
        self.fallback_exchange = ccxt.kraken({"enableRateLimit": True})  # Fallback exchange
        self.last_price = Decimal("0.0")
        self.last_update = None

    async def get_btc_price(self) -> Decimal:
        """Get BTC price with fallback providers."""
        try:
            # Try primary provider (Binance)
            ticker = await self.primary_exchange.fetch_ticker("BTC/USDT")
            price = Decimal(str(ticker["last"]))
            self.last_price = price
            self.last_update = datetime.now(timezone.utc)
            return price
        except Exception as e:
            logger.warning(f"Primary price feed failed: {e}")
            try:
                # Try fallback provider (Kraken)
                ticker = await self.fallback_exchange.fetch_ticker("BTC/USD")
                price = Decimal(str(ticker["last"]))
                self.last_price = price
                self.last_update = datetime.now(timezone.utc)
                logger.info("Using fallback price feed (Kraken)")
                return price
            except Exception as e2:
                logger.error(f"Fallback price feed also failed: {e2}")
                # Return last known price if both fail
                if self.last_price > 0:
                    logger.warning("Using stale price data")
                    return self.last_price
                raise RuntimeError("All price feeds failed")

    async def close(self):
        """Close exchange connections."""
        await self.primary_exchange.close()
        await self.fallback_exchange.close()
class Position:
    __slots__ = ("market_id", "title", "side", "size", "entry_price",
                 "entry_btc", "entry_time")

    def __init__(self, market_id, title, side, size, entry_price, entry_btc):
        self.market_id   = market_id
        self.title       = title
        self.side        = side
        self.size        = size
        self.entry_price = entry_price
        self.entry_btc   = entry_btc
        self.entry_time  = datetime.now(timezone.utc)


class PerformanceTracker:
    """Tracks cumulative performance metrics in real-time."""

    def __init__(self, initial_balance: Decimal):
        self.initial_balance = initial_balance
        self.balance         = initial_balance
        self.trades: List[Dict] = []          # [{pnl, exit_reason, timestamp}]
        self.equity_curve: List[float] = [float(initial_balance)]

    def record_trade(self, pnl: Decimal, exit_reason: str):
        self.balance += pnl
        self.trades.append({
            "pnl":         pnl,
            "exit_reason": exit_reason,
            "timestamp":   datetime.now(timezone.utc),
        })
        self.equity_curve.append(float(self.balance))

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> List[Dict]:
        return [t for t in self.trades if t["pnl"] > 0]

    @property
    def losses(self) -> List[Dict]:
        return [t for t in self.trades if t["pnl"] <= 0]

    @property
    def win_rate(self) -> float:
        return len(self.wins) / self.n * 100 if self.n else 0.0

    @property
    def total_pnl(self) -> Decimal:
        return sum(t["pnl"] for t in self.trades) if self.trades else Decimal("0")

    @property
    def avg_win(self) -> Decimal:
        return sum(t["pnl"] for t in self.wins) / len(self.wins) if self.wins else Decimal("0")

    @property
    def avg_loss(self) -> Decimal:
        return sum(t["pnl"] for t in self.losses) / len(self.losses) if self.losses else Decimal("0")

    @property
    def max_drawdown(self) -> float:
        """Peak-to-trough drawdown as a fraction."""
        peak = max(self.equity_curve) if self.equity_curve else float(self.initial_balance)
        trough_after_peak = float(self.balance)
        dd = (peak - trough_after_peak) / peak if peak > 0 else 0.0
        return max(0.0, dd)

    @property
    def sharpe(self) -> float:
        if self.n < 2:
            return 0.0
        pnls  = [float(t["pnl"]) for t in self.trades]
        mean  = sum(pnls) / self.n
        var   = sum((x - mean) ** 2 for x in pnls) / self.n
        std   = math.sqrt(var) if var > 0 else 1e-9
        # Annualised: 288 × 5-min bars per day × 252 trading days
        return (mean / std) * math.sqrt(288 * 252)

    @property
    def profit_factor(self) -> float:
        gross_win  = float(sum(t["pnl"] for t in self.wins))
        gross_loss = abs(float(sum(t["pnl"] for t in self.losses)))
        return gross_win / gross_loss if gross_loss > 0 else float("inf")

    def deep_stats_text(self) -> str:
        """Rich Telegram-formatted deep performance stats block."""
        if not self.trades:
            return "_No closed trades yet._"

        pnl_sign = "📈" if self.total_pnl >= 0 else "📉"
        exit_counts: Dict[str, int] = {}
        for t in self.trades:
            k = t["exit_reason"]
            exit_counts[k] = exit_counts.get(k, 0) + 1

        exit_str = "  ".join(f"`{k}`: {v}" for k, v in exit_counts.items())

        return (
            "🧮 *Deep Performance Stats*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"├─ Closed Trades: `{self.n}`\n"
            f"├─ Win Rate:      `{self.win_rate:.1f}%`\n"
            f"├─ {pnl_sign} Total P&L:  `{float(self.total_pnl):+.4f}` USDC\n"
            f"├─ Avg Win:       `{float(self.avg_win):+.4f}` USDC\n"
            f"├─ Avg Loss:      `{float(self.avg_loss):+.4f}` USDC\n"
            f"├─ Profit Factor: `{self.profit_factor:.3f}`\n"
            f"├─ Max Drawdown:  `{self.max_drawdown*100:.2f}%`\n"
            f"├─ Sharpe Ratio:  `{self.sharpe:.3f}`\n"
            f"└─ Exit Types:    {exit_str}"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN BOT CLASS
# ─────────────────────────────────────────────────────────────────────────────
class TradingBot:
    def __init__(self):
        # ── Config ────────────────────────────────────────────────────────
        self.mode             = os.getenv("TRADING_MODE", "DRY_RUN")
        self.edge_threshold   = Decimal(os.getenv("EDGE_THRESHOLD", "0.10"))
        self.max_position_size = Decimal(os.getenv("MAX_POSITION_SIZE", "10.0"))
        self.stop_loss_pct    = Decimal(os.getenv("STOP_LOSS_PCT", "0.05"))
        self.take_profit_pct  = Decimal(os.getenv("TAKE_PROFIT_PCT", "0.15"))
        self.pnl_alert_threshold = Decimal(os.getenv("PNL_ALERT_THRESHOLD", "5.0"))  # USDC

        # Strategy toggles
        self.enable_arbitrage = os.getenv("ENABLE_ARBITRAGE", "true").lower() == "true"
        self.enable_oracle_snipe = os.getenv("ENABLE_ORACLE_SNIPE", "true").lower() == "true"
        self.enable_momentum = os.getenv("ENABLE_MOMENTUM", "true").lower() == "true"
        self.enable_cross_market = os.getenv("ENABLE_CROSS_MARKET", "false").lower() == "true"
        self.enable_asymmetric = os.getenv("ENABLE_ASYMMETRIC", "true").lower() == "true"

        # Strategy parameters
        self.arb_sum_target = Decimal(os.getenv("ARB_SUM_TARGET", "0.96"))
        self.oracle_snipe_window = int(os.getenv("ORACLE_SNIPE_WINDOW", "30"))  # seconds
        self.momentum_threshold = Decimal(os.getenv("MOMENTUM_THRESHOLD", "0.08"))
        self.cross_market_threshold = Decimal(os.getenv("CROSS_MARKET_THRESHOLD", "0.05"))
        self.asymmetric_edge_threshold = Decimal(os.getenv("ASYMMETRIC_EDGE_THRESHOLD", "0.08"))

        self.telegram_token   = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_user_id  = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

        # ── State ─────────────────────────────────────────────────────────
        self.is_paused        = False
        self.active_markets: Dict[str, dict]   = {}
        self.active_positions: Dict[str, Position] = {}
        self.btc_price        = Decimal("0.0")
        self.sigma_proxy      = Decimal("100.0")
        self.dashboard_msg_id = None
        self.cumulative_pnl   = Decimal("0.0")
        self.last_alert_pnl   = Decimal("0.0")
        self.log_lines: List[str] = []

        # Performance tracking
        self.perf = PerformanceTracker(Decimal(os.getenv("INITIAL_BALANCE", "5000.0")))

        # ── Clients ───────────────────────────────────────────────────────
        self.clob_client: Optional[object] = None
        self.price_feed = PriceFeed()
        self.tg_app: Optional[Application] = None

    # ─────────────────────────────────────────────────────────────────────
    #  UTILITIES
    # ─────────────────────────────────────────────────────────────────────
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.log_lines.append(entry)
        if len(self.log_lines) > 8:
            self.log_lines.pop(0)
        logger.info(msg)

    def _prob(self, btc: Decimal, strike: Decimal, time_left_s: float) -> Decimal:
        clamped = max(0.1, time_left_s / 300.0)
        tf      = Decimal(str(math.sqrt(clamped)))
        z       = (btc - strike) / (self.sigma_proxy * tf)
        p       = Decimal("0.5") + (z / Decimal("2.0"))
        return max(Decimal("0.01"), min(Decimal("0.99"), p))

    @staticmethod
    def _esc(text: str) -> str:
        """Escape Telegram MarkdownV2 special chars."""
        for ch in r"\_*[]()~`>#+-=|{}.!":
            text = text.replace(ch, f"\\{ch}")
        return text

    # ─────────────────────────────────────────────────────────────────────
    #  INITIALISATION
    # ─────────────────────────────────────────────────────────────────────
    async def init_polymarket(self):
        if not ClobClient:
            self.log("clob_client not installed → simulation mode")
            return False
        pk      = os.getenv("POLYMARKET_PK")
        address = os.getenv("POLYMARKET_ADDRESS", "0xc7b9939135F5143D5b9eB968cf6f93566E31ff52")
        key     = os.getenv("POLYMARKET_API_KEY")
        phrase  = os.getenv("POLYMARKET_API_PASSPHRASE")
        secret  = os.getenv("POLYMARKET_API_SECRET")
        if not pk:
            self.log("POLYMARKET_PK not set → simulation mode")
            return False
        try:
            creds = ApiCredential(key=key, passphrase=phrase, secret=secret)
            self.clob_client = ClobClient(
                "https://clob.polymarket.com",
                key=pk, chain_id=POLYGON, funder=address, creds=creds,
            )
            self.log(f"Polymarket CLOB connected — mode: {self.mode}")
            return True
        except Exception as e:
            self.log(f"Polymarket init error: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    #  BACKGROUND LOOPS
    # ─────────────────────────────────────────────────────────────────────
    async def price_feed_loop(self):
        while True:
            try:
                self.btc_price = await self.price_feed.get_btc_price()
            except Exception as e:
                self.log(f"Price feed error: {e}")
            await asyncio.sleep(1)

    async def market_discovery_loop(self):
        url = "https://gamma-api.polymarket.com/markets"
        while True:
            try:
                r = requests.get(url, params={"active": "true", "closed": "false",
                                              "query": "Bitcoin 5 minutes"}, timeout=10)
                if r.ok:
                    found = {
                        m["id"]: m for m in r.json()
                        if "Bitcoin" in m.get("title", "") and "5 minutes" in m.get("title", "")
                    }
                    self.active_markets = found
                    self.log(f"Discovered {len(found)} 5-min BTC markets")
                else:
                    self.log(f"Gamma API {r.status_code}")
            except Exception as e:
                self.log(f"Market discovery error: {e}")
            await asyncio.sleep(60)

    # ─────────────────────────────────────────────────────────────────────
    #  TRADING ENGINE
    # ─────────────────────────────────────────────────────────────────────
    async def trading_loop(self):
        while True:
            if self.is_paused:
                await asyncio.sleep(2)
                continue
            try:
                if self.active_markets:
                    await self._manage_positions()
                    await self._run_strategies()
            except Exception as e:
                self.log(f"Trading loop error: {e}")
            await asyncio.sleep(1)  # Faster polling for strategies

    async def _run_strategies(self):
        """Run all enabled trading strategies."""
        for mid, market in self.active_markets.items():
            if self.enable_arbitrage:
                await self._arbitrage_strategy(mid, market)
            if self.enable_oracle_snipe:
                await self._oracle_snipe_strategy(mid, market)
            if self.enable_momentum:
                await self._momentum_strategy(mid, market)
            if self.enable_cross_market:
                await self._cross_market_strategy(mid, market)
            if self.enable_asymmetric:
                await self._asymmetric_strategy(mid, market)
        for mid, market in self.active_markets.items():
            if mid in self.active_positions:
                continue
            title  = market.get("title", "")
            tokens = market.get("tokens", [])
            if len(tokens) < 2:
                continue
            try:
                strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
                strike     = Decimal(strike_str)
                exp_str    = market.get("expires_at", "")
                if not exp_str:
                    continue
                exp_dt     = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                time_left  = (exp_dt - datetime.now(timezone.utc)).total_seconds()
                if time_left <= 30:
                    continue

                prob_y     = self._prob(self.btc_price, strike, time_left)
                # Simulated spread of 4 cts
                price_yes  = prob_y - Decimal("0.02")
                price_no   = (1 - prob_y) - Decimal("0.02")

                if (prob_y - price_yes) >= self.edge_threshold:
                    await self._open_position(mid, title, "YES", price_yes, prob_y)
                elif ((1 - prob_y) - price_no) >= self.edge_threshold:
                    await self._open_position(mid, title, "NO", price_no, 1 - prob_y)

            except Exception as e:
                logger.debug(f"Scan entry error {mid}: {e}")

    async def _open_position(self, mid, title, side, price, prob):
        edge = prob - price
        pos  = Position(mid, title, side, self.max_position_size, price, self.btc_price)
        self.active_positions[mid] = pos

        self.log(f"OPEN {side} | {title[:30]} | Edge {float(edge)*100:.1f}%")

        # Real order placement hook
        if self.mode == "LIVE" and self.clob_client:
            try:
                # await self.clob_client.create_order(...)
                pass
            except Exception as e:
                self.log(f"ORDER_ERROR: {e}")

        await self._send_alert(
            f"🚀 *TRADE OPENED*\n"
            f"├─ Market: `{self._esc(title[:40])}`\n"
            f"├─ Side:   `{side}`\n"
            f"├─ Entry:  `${float(price):.3f}`\n"
            f"├─ Prob:   `{float(prob)*100:.1f}%`\n"
            f"└─ Edge:   `{float(edge)*100:.1f}%`"
        )

    async def _manage_positions(self):
        to_close: List[str] = []

        for mid, pos in list(self.active_positions.items()):
            market = self.active_markets.get(mid)
            if not market:
                to_close.append(mid)
                continue
            try:
                exp_str   = market.get("expires_at", "")
                exp_dt    = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                time_left = (exp_dt - datetime.now(timezone.utc)).total_seconds()

                if time_left <= 0:
                    # Resolution
                    strike    = Decimal(pos.title.split("$")[1].split(" ")[0].replace(",", ""))
                    is_win    = (self.btc_price > strike and pos.side == "YES") or \
                                (self.btc_price < strike and pos.side == "NO")
                    exit_p    = Decimal("1.0") if is_win else Decimal("0.0")
                    pnl       = pos.size * (exit_p - pos.entry_price)
                    reason    = "EXPIRY_WIN" if is_win else "EXPIRY_LOSS"
                    await self._close_position(mid, pos, pnl, exit_p, reason)
                    to_close.append(mid)
                    continue

                curr_prob  = self._prob(self.btc_price,
                                        Decimal(pos.title.split("$")[1].split(" ")[0].replace(",", "")),
                                        time_left)
                mkt_price  = curr_prob if pos.side == "YES" else (1 - curr_prob)

                sl_price = pos.entry_price * (1 - self.stop_loss_pct)
                tp_price = pos.entry_price + (1 - pos.entry_price) * self.take_profit_pct

                if mkt_price <= sl_price:
                    pnl = pos.size * (mkt_price - pos.entry_price)
                    await self._close_position(mid, pos, pnl, mkt_price, "STOP_LOSS")
                    to_close.append(mid)
                elif mkt_price >= tp_price:
                    pnl = pos.size * (mkt_price - pos.entry_price)
                    await self._close_position(mid, pos, pnl, mkt_price, "TAKE_PROFIT")
                    to_close.append(mid)

            except Exception as e:
                logger.debug(f"Manage position error {mid}: {e}")

        for mid in to_close:
            self.active_positions.pop(mid, None)

    # ─────────────────────────────────────────────────────────────────────
    #  TRADING STRATEGIES
    # ─────────────────────────────────────────────────────────────────────
    async def _arbitrage_strategy(self, mid: str, market: dict):
        """Risk-free arbitrage: Buy both sides if sum < target."""
        if mid in self.active_positions:
            return
        try:
            tokens = market.get("tokens", [])
            if len(tokens) < 2:
                return
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
            if not yes_token or not no_token:
                return

            yes_price = Decimal(str(yes_token.get("price", 0)))
            no_price = Decimal(str(no_token.get("price", 0)))
            total_cost = yes_price + no_price

            if total_cost <= self.arb_sum_target:
                edge = (Decimal("1.0") - total_cost) / Decimal("2.0")  # Split edge
                await self._open_position(mid, market.get("title", ""), "ARB_YES", yes_price, Decimal("0.5"))
                await self._open_position(mid, market.get("title", ""), "ARB_NO", no_price, Decimal("0.5"))
                self.log(f"ARB OPEN | {market.get('title', '')[:30]} | Total Cost {float(total_cost):.3f}")
        except Exception as e:
            logger.debug(f"Arbitrage error {mid}: {e}")

    async def _oracle_snipe_strategy(self, mid: str, market: dict):
        """Last-second sniping based on oracle latency."""
        if mid in self.active_positions:
            return
        try:
            exp_str = market.get("expires_at", "")
            if not exp_str:
                return
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            time_left = (exp_dt - datetime.now(timezone.utc)).total_seconds()

            if time_left > self.oracle_snipe_window:
                return  # Too early

            title = market.get("title", "")
            strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
            strike = Decimal(strike_str)

            # Simple momentum: if BTC moved significantly towards strike
            prob_up = self._prob(self.btc_price, strike, time_left)
            implied_prob = prob_up if self.btc_price > strike else (1 - prob_up)

            if implied_prob > Decimal("0.6"):  # Strong signal
                side = "YES" if self.btc_price > strike else "NO"
                price = prob_up if side == "YES" else (1 - prob_up)
                if price < Decimal("0.5"):  # Cheap
                    await self._open_position(mid, title, side, price, implied_prob)
                    self.log(f"ORACLE SNIPE | {title[:30]} | Side {side} | Prob {float(implied_prob)*100:.1f}%")
        except Exception as e:
            logger.debug(f"Oracle snipe error {mid}: {e}")

    async def _momentum_strategy(self, mid: str, market: dict):
        """Statistical momentum edge."""
        if mid in self.active_positions:
            return
        try:
            title = market.get("title", "")
            tokens = market.get("tokens", [])
            if len(tokens) < 2:
                return
            strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
            strike = Decimal(strike_str)
            exp_str = market.get("expires_at", "")
            if not exp_str:
                return
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            time_left = (exp_dt - datetime.now(timezone.utc)).total_seconds()

            prob_y = self._prob(self.btc_price, strike, time_left)
            price_yes = prob_y - Decimal("0.02")
            price_no = (1 - prob_y) - Decimal("0.02")

            if (prob_y - price_yes) >= self.momentum_threshold:
                await self._open_position(mid, title, "YES", price_yes, prob_y)
            elif ((1 - prob_y) - price_no) >= self.momentum_threshold:
                await self._open_position(mid, title, "NO", price_no, 1 - prob_y)
        except Exception as e:
            logger.debug(f"Momentum error {mid}: {e}")

    async def _cross_market_strategy(self, mid: str, market: dict):
        """Cross-market correlation arbitrage."""
        # Simplified: Compare with other active markets
        if mid in self.active_positions:
            return
        try:
            title = market.get("title", "")
            tokens = market.get("tokens", [])
            if len(tokens) < 2:
                return
            strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
            strike = Decimal(strike_str)

            # Compare implied probs across markets
            probs = []
            for other_mid, other_market in self.active_markets.items():
                if other_mid == mid:
                    continue
                try:
                    other_title = other_market.get("title", "")
                    other_strike_str = other_title.split("$")[1].split(" ")[0].replace(",", "")
                    other_strike = Decimal(other_strike_str)
                    other_exp_str = other_market.get("expires_at", "")
                    if not other_exp_str:
                        continue
                    other_exp_dt = datetime.fromisoformat(other_exp_str.replace("Z", "+00:00"))
                    other_time_left = (other_exp_dt - datetime.now(timezone.utc)).total_seconds()
                    other_prob = self._prob(self.btc_price, other_strike, other_time_left)
                    probs.append(other_prob)
                except:
                    continue

            if probs:
                avg_prob = sum(probs) / len(probs)
                current_prob = self._prob(self.btc_price, strike, (datetime.fromisoformat(market.get("expires_at", "").replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds())
                divergence = abs(current_prob - avg_prob)
                if divergence >= self.cross_market_threshold:
                    side = "YES" if current_prob > avg_prob else "NO"
                    price = current_prob if side == "YES" else (1 - current_prob)
                    await self._open_position(mid, title, side, price, current_prob)
                    self.log(f"CROSS MARKET | {title[:30]} | Divergence {float(divergence)*100:.1f}%")
        except Exception as e:
            logger.debug(f"Cross market error {mid}: {e}")

    async def _asymmetric_strategy(self, mid: str, market: dict):
        """Asymmetric cheap-side sniping."""
        if mid in self.active_positions:
            return
        try:
            title = market.get("title", "")
            tokens = market.get("tokens", [])
            if len(tokens) < 2:
                return
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
            if not yes_token or not no_token:
                return

            yes_price = Decimal(str(yes_token.get("price", 0)))
            no_price = Decimal(str(no_token.get("price", 0)))

            strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
            strike = Decimal(strike_str)
            exp_str = market.get("expires_at", "")
            if not exp_str:
                return
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            time_left = (exp_dt - datetime.now(timezone.utc)).total_seconds()

            prob_y = self._prob(self.btc_price, strike, time_left)
            edge_yes = prob_y - yes_price
            edge_no = (1 - prob_y) - no_price

            if edge_yes >= self.asymmetric_edge_threshold and edge_yes > edge_no:
                await self._open_position(mid, title, "YES", yes_price, prob_y)
            elif edge_no >= self.asymmetric_edge_threshold and edge_no > edge_yes:
                await self._open_position(mid, title, "NO", no_price, 1 - prob_y)
        except Exception as e:
            logger.debug(f"Asymmetric error {mid}: {e}")

    async def _close_position(self, mid, pos: Position, pnl: Decimal, exit_price: Decimal, reason: str):
        self.cumulative_pnl += pnl
        self.perf.record_trade(pnl, reason)
        self.log(f"CLOSE {reason} | {pos.title[:30]} | PnL {float(pnl):+.4f}")

        emoji = "🎯" if reason == "TAKE_PROFIT" else ("🛑" if reason == "STOP_LOSS" else ("✅" if pnl > 0 else "❌"))
        await self._send_alert(
            f"{emoji} *{reason.replace('_', ' ')}*\n"
            f"├─ Market: `{self._esc(pos.title[:40])}`\n"
            f"├─ Side:   `{pos.side}`\n"
            f"├─ Entry:  `${float(pos.entry_price):.3f}`\n"
            f"├─ Exit:   `${float(exit_price):.3f}`\n"
            f"├─ PnL:    `{float(pnl):+.4f}` USDC\n"
            f"└─ Total:  `{float(self.cumulative_pnl):+.4f}` USDC"
        )
        await self._check_pnl_threshold_alert()

    async def _check_pnl_threshold_alert(self):
        """Send alert if cumulative P&L has moved by more than the threshold since last alert."""
        delta = abs(self.cumulative_pnl - self.last_alert_pnl)
        if delta >= self.pnl_alert_threshold:
            direction = "🟢 GAIN" if self.cumulative_pnl > self.last_alert_pnl else "🔴 LOSS"
            await self._send_alert(
                f"🔔 *P&L THRESHOLD ALERT*\n"
                f"├─ Direction:   `{direction}`\n"
                f"├─ Session P&L: `{float(self.cumulative_pnl):+.4f}` USDC\n"
                f"├─ Δ Since last: `{float(delta):+.4f}` USDC\n"
                f"└─ Win Rate:    `{self.perf.win_rate:.1f}%`"
            )
            self.last_alert_pnl = self.cumulative_pnl

    # ─────────────────────────────────────────────────────────────────────
    #  TELEGRAM HELPERS
    # ─────────────────────────────────────────────────────────────────────
    async def _send_alert(self, message: str):
        if not self.tg_app or not self.allowed_user_id:
            return
        try:
            await self.tg_app.bot.send_message(
                chat_id=self.allowed_user_id,
                text=message,
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.warning(f"Alert send failed: {e}")

    def _dashboard_text(self) -> str:
        status = "🟢 ACTIVE" if not self.is_paused else "🟡 PAUSED"
        mode   = "🛑 LIVE"   if self.mode == "LIVE"  else "🧪 DRY\\-RUN"
        btc    = self._esc(f"${float(self.btc_price):,.2f}")
        bal    = self._esc(f"{float(self.perf.balance):,.2f}")
        pnl    = self._esc(f"{float(self.cumulative_pnl):+.4f}")
        wr     = self._esc(f"{self.perf.win_rate:.1f}")
        pf     = self._esc(f"{self.perf.profit_factor:.3f}")
        mdd    = self._esc(f"{self.perf.max_drawdown*100:.2f}")
        cnt    = self.perf.n
        pos_n  = len(self.active_positions)
        mkts   = len(self.active_markets)

        pos_lines = ""
        for pos in list(self.active_positions.values())[:3]:
            pos_lines += (
                f"├─ `{pos.side}` · `{self._esc(pos.title[:20])}…` "
                f"@ `{float(pos.entry_price):.3f}`\n"
            )
        if pos_n > 3:
            pos_lines += f"└─ _\\+{pos_n - 3} more_\n"
        if pos_n == 0:
            pos_lines = "└─ _None_\n"

        logs = "\n".join(self.log_lines[-5:]) if self.log_lines else "(no activity)"

        text = (
            f"🤖 *RECON HFT* \\| {status}\n"
            f"⚡ Mode: {mode} \\| 📡 Markets: `{mkts}`\n"
            f"📈 BTC: `{btc}`\n"
            f"🎯 Strategies: Arb`{'✅' if self.enable_arbitrage else '❌'}` "
            f"Oracle`{'✅' if self.enable_oracle_snipe else '❌'}` "
            f"Mom`{'✅' if self.enable_momentum else '❌'}`\n\n"
            f"💰 *Portfolio Summary*\n"
            f"├─ Balance:   `{bal}` USDC\n"
            f"├─ Session P&L: `{pnl}` USDC\n"
            f"├─ Win Rate:  `{wr}%` \\({cnt} trades\\)\n"
            f"├─ Profit Factor: `{pf}`\n"
            f"└─ Max Drawdown:  `{mdd}%`\n\n"
            f"📂 *Active Positions* \\({pos_n}\\)\n{pos_lines}\n"
            f"📋 *Latest Activity*\n"
            f"```\n{logs}\n```"
        )
        return text

    # ─────────────────────────────────────────────────────────────────────
    #  TELEGRAM COMMANDS
    # ─────────────────────────────────────────────────────────────────────
    async def start_telegram(self):
        self.tg_app = Application.builder().token(self.telegram_token).build()
        handlers = [
            ("start",        self.cmd_start),
            ("status",       self.cmd_status),
            ("stats",        self.cmd_stats),
            ("pause",        self.cmd_pause),
            ("resume",       self.cmd_resume),
            ("backtest",     self.cmd_backtest),
            ("setthreshold", self.cmd_set_threshold),
            ("setsl",        self.cmd_set_sl),
            ("settp",        self.cmd_set_tp),
            ("setpnl",       self.cmd_set_pnl_alert),
            ("positions",    self.cmd_positions),
            ("togglearb",    self.cmd_toggle_arbitrage),
            ("toggleoracle", self.cmd_toggle_oracle),
            ("togglemomentum", self.cmd_toggle_momentum),
            ("togglecross",  self.cmd_toggle_cross),
            ("toggleasym",   self.cmd_toggle_asymmetric),
            ("strategies",   self.cmd_strategies),
        ]
        for name, fn in handlers:
            self.tg_app.add_handler(CommandHandler(name, fn))
        self.tg_app.add_handler(CallbackQueryHandler(self._handle_cb))
        await self.tg_app.initialize()
        await self.tg_app.start()
        await self.tg_app.updater.start_polling()
        self.log("Telegram bot started")

    def _require_auth(fn):
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_user.id != self.allowed_user_id:
                await update.message.reply_text("⛔ Unauthorized.")
                return
            return await fn(self, update, context)
        return wrapper

    @_require_auth
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
             InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle")],
            [InlineKeyboardButton("📊 Deep Stats", callback_data="stats"),
             InlineKeyboardButton("📂 Positions", callback_data="positions")],
        ]
        msg = await update.message.reply_text(
            self._dashboard_text(),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        self.dashboard_msg_id = msg.message_id
        asyncio.create_task(self._dashboard_loop(context))

    @_require_auth
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self._dashboard_text(), parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send deep performance stats."""
        raw = self.perf.deep_stats_text()
        # Escape any remaining special chars that weren't already escaped
        await update.message.reply_text(raw, parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.active_positions:
            await update.message.reply_text("📂 _No open positions\\._", parse_mode="MarkdownV2")
            return
        lines = ["📂 *Open Positions*\n━━━━━━━━━━━━━━━━━━"]
        for pos in self.active_positions.values():
            age = (datetime.now(timezone.utc) - pos.entry_time).seconds
            lines.append(
                f"• `{pos.side}` · `{self._esc(pos.title[:35])}`\n"
                f"  Entry `${float(pos.entry_price):.3f}` · Age `{age}s`"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = True
        self.log("Bot paused by user")
        await update.message.reply_text("🟡 Bot *PAUSED*\\.", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = False
        self.log("Bot resumed by user")
        await update.message.reply_text("🟢 Bot *RESUMED*\\.", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_set_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            v = Decimal(context.args[0])
            self.edge_threshold = v
            await update.message.reply_text(f"✅ Edge threshold → `{v}`", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: /setthreshold 0.10")

    @_require_auth
    async def cmd_set_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            v = Decimal(context.args[0])
            self.stop_loss_pct = v
            await update.message.reply_text(f"✅ Stop-loss → `{v}`", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: /setsl 0.05")

    @_require_auth
    async def cmd_set_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            v = Decimal(context.args[0])
            self.take_profit_pct = v
            await update.message.reply_text(f"✅ Take-profit → `{v}`", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: /settp 0.15")

    @_require_auth
    async def cmd_set_pnl_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            v = Decimal(context.args[0])
            self.pnl_alert_threshold = v
            await update.message.reply_text(f"✅ P&L alert threshold → `{v}` USDC", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: /setpnl 5.0")

    @_require_auth
    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run a full backtest and return formatted results."""
        # Parse optional candle count: /backtest 2000
        limit = 1500
        if context.args:
            try:
                limit = int(context.args[0])
                limit = max(100, min(3000, limit))
            except ValueError:
                pass

        await update.message.reply_text(
            f"⏳ *Running backtest on {limit} × 1m candles…*\nThis may take 20\\-30s\\.",
            parse_mode="MarkdownV2",
        )

        try:
            # Support both `python bot/main.py` and `python -m bot.main`
            try:
                from bot.backtest import Backtester
            except ModuleNotFoundError:
                from backtest import Backtester
            bt = Backtester(
                limit=limit,
                edge_threshold=float(self.edge_threshold),
                stop_loss_pct=float(self.stop_loss_pct),
                take_profit_pct=float(self.take_profit_pct),
                position_size=float(self.max_position_size),
                initial_balance=float(self.perf.initial_balance),
            )
            await bt.run()
            report_text = bt.format_telegram_report()
            await update.message.reply_text(report_text, parse_mode="MarkdownV2")
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Backtest failed: {self._esc(str(e))}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_toggle_arbitrage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.enable_arbitrage = not self.enable_arbitrage
        status = "ENABLED" if self.enable_arbitrage else "DISABLED"
        await update.message.reply_text(f"✅ Arbitrage strategy {status}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_toggle_oracle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.enable_oracle_snipe = not self.enable_oracle_snipe
        status = "ENABLED" if self.enable_oracle_snipe else "DISABLED"
        await update.message.reply_text(f"✅ Oracle snipe strategy {status}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_toggle_momentum(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.enable_momentum = not self.enable_momentum
        status = "ENABLED" if self.enable_momentum else "DISABLED"
        await update.message.reply_text(f"✅ Momentum strategy {status}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_toggle_cross(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.enable_cross_market = not self.enable_cross_market
        status = "ENABLED" if self.enable_cross_market else "DISABLED"
        await update.message.reply_text(f"✅ Cross-market strategy {status}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_toggle_asymmetric(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.enable_asymmetric = not self.enable_asymmetric
        status = "ENABLED" if self.enable_asymmetric else "DISABLED"
        await update.message.reply_text(f"✅ Asymmetric strategy {status}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        lines = ["🤖 *Strategy Status*\n━━━━━━━━━━━━━━━━━━"]
        lines.append(f"├─ Arbitrage:     `{'✅' if self.enable_arbitrage else '❌'}`")
        lines.append(f"├─ Oracle Snipe:  `{'✅' if self.enable_oracle_snipe else '❌'}`")
        lines.append(f"├─ Momentum:      `{'✅' if self.enable_momentum else '❌'}`")
        lines.append(f"├─ Cross-Market:  `{'✅' if self.enable_cross_market else '❌'}`")
        lines.append(f"└─ Asymmetric:    `{'✅' if self.enable_asymmetric else '❌'}`")
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")

    async def _handle_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
             InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle")],
            [InlineKeyboardButton("📊 Deep Stats", callback_data="stats"),
             InlineKeyboardButton("📂 Positions", callback_data="positions")],
        ])
        if q.data == "refresh":
            await q.edit_message_text(self._dashboard_text(), parse_mode="MarkdownV2", reply_markup=keyboard)
        elif q.data == "toggle":
            self.is_paused = not self.is_paused
            self.log(f"Bot {'PAUSED' if self.is_paused else 'RESUMED'} via dashboard")
            await q.edit_message_text(self._dashboard_text(), parse_mode="MarkdownV2", reply_markup=keyboard)
        elif q.data == "stats":
            await self.tg_app.bot.send_message(
                chat_id=self.allowed_user_id,
                text=self.perf.deep_stats_text(),
                parse_mode="MarkdownV2",
            )
        elif q.data == "positions":
            pos_text = "📂 *Positions*\n"
            for p in self.active_positions.values():
                pos_text += f"• `{p.side}` · `{self._esc(p.title[:30])}`\n"
            if not self.active_positions:
                pos_text += "_None open_"
            await self.tg_app.bot.send_message(
                chat_id=self.allowed_user_id, text=pos_text, parse_mode="MarkdownV2"
            )

    async def _dashboard_loop(self, context: ContextTypes.DEFAULT_TYPE):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
             InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle")],
            [InlineKeyboardButton("📊 Deep Stats", callback_data="stats"),
             InlineKeyboardButton("📂 Positions", callback_data="positions")],
        ])
        while True:
            await asyncio.sleep(15)
            if self.dashboard_msg_id and self.allowed_user_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=self.allowed_user_id,
                        message_id=self.dashboard_msg_id,
                        text=self._dashboard_text(),
                        parse_mode="MarkdownV2",
                        reply_markup=keyboard,
                    )
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    bot = TradingBot()
    try:
        await bot.init_polymarket()
        await asyncio.gather(
            bot.start_telegram(),
            bot.price_feed_loop(),
            bot.market_discovery_loop(),
            bot.trading_loop(),
        )
    finally:
        await bot.price_feed.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — RECON HFT stopped.")