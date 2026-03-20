"""
RECON HFT Bot — Polymarket 5-min BTC Markets
Strategy: Bayesian Z-Score with SL/TP, Backtesting, and Telegram Intelligence Dashboard
"""
import asyncio
import os
import math
import logging
import requests
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# ── Optional CLOB client ────────────────────────────────────────────────────
try:
    from clob_client.client import ClobClient
    from clob_client.clob_types import OrderArgs, ApiCredential
    from clob_client.constants import POLYGON
except ImportError:
    ClobClient = None  # Trading will be simulated

# ── Telegram ────────────────────────────────────────────────────────────────
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ── Price feed ──────────────────────────────────────────────────────────────
import ccxt.async_support as ccxt

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
load_dotenv()


# ════════════════════════════════════════════════════════════════════════════
#  PERFORMANCE TRACKER — per-trade record keeping
# ════════════════════════════════════════════════════════════════════════════
class PerformanceTracker:
    def __init__(self):
        self.trades: List[Dict] = []  # list of {pnl, edge, side, timestamp}
        self.peak_balance: Decimal = Decimal("5000.0")
        self.max_drawdown: Decimal = Decimal("0.0")
        self.balance: Decimal = Decimal("5000.0")

    def record(self, pnl: Decimal, edge: Decimal, side: str, title: str):
        self.trades.append({
            "pnl": pnl,
            "edge": edge,
            "side": side,
            "title": title,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.balance += pnl
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        drawdown = (self.peak_balance - self.balance) / self.peak_balance * 100
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t["pnl"] > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t["pnl"] <= 0)

    @property
    def win_rate(self) -> float:
        if not self.total_trades:
            return 0.0
        return self.wins / self.total_trades * 100

    @property
    def total_pnl(self) -> Decimal:
        return sum(t["pnl"] for t in self.trades) if self.trades else Decimal("0")

    @property
    def avg_profit(self) -> Decimal:
        winning = [t["pnl"] for t in self.trades if t["pnl"] > 0]
        return sum(winning) / len(winning) if winning else Decimal("0")

    @property
    def avg_loss(self) -> Decimal:
        losing = [t["pnl"] for t in self.trades if t["pnl"] <= 0]
        return sum(losing) / len(losing) if losing else Decimal("0")

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        return float(gross_profit / gross_loss) if gross_loss else float("inf")

    @property
    def sharpe_ratio(self) -> float:
        """Simplified Sharpe: mean / std of trade PnLs (annualised proxy)."""
        if len(self.trades) < 2:
            return 0.0
        pnls = [float(t["pnl"]) for t in self.trades]
        mean = sum(pnls) / len(pnls)
        variance = sum((x - mean) ** 2 for x in pnls) / len(pnls)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        return mean / std * math.sqrt(252)  # Annualised

    @property
    def roi(self) -> float:
        return float(self.total_pnl / Decimal("5000.0") * 100)


# ════════════════════════════════════════════════════════════════════════════
#  BACKTESTER — historical simulation against Binance 1m candles
# ════════════════════════════════════════════════════════════════════════════
class Backtester:
    def __init__(self, edge_threshold=0.10, stop_loss_pct=0.05, take_profit_pct=0.15, candles=500):
        self.edge_threshold = Decimal(str(edge_threshold))
        self.stop_loss_pct = Decimal(str(stop_loss_pct))
        self.take_profit_pct = Decimal(str(take_profit_pct))
        self.candles = candles
        self.sigma = Decimal("100.0")
        self.perf = PerformanceTracker()
        self.exchange = ccxt.binance()

    def _calc_prob(self, btc: Decimal, strike: Decimal, time_left: float) -> Decimal:
        tf = Decimal(str(max(0.05, time_left / 300.0))).sqrt()
        z = (btc - strike) / (self.sigma * tf)
        p = Decimal("0.5") + (z / Decimal("2.0"))
        return max(Decimal("0.01"), min(Decimal("0.99"), p))

    async def run(self) -> "PerformanceTracker":
        logger.info(f"Backtester: fetching {self.candles} BTC/USDT 1m candles…")
        try:
            ohlcv = await self.exchange.fetch_ohlcv("BTC/USDT", "1m", limit=self.candles)
        finally:
            await self.exchange.close()

        active_positions: List[Dict] = []

        for i, (ts, o, h, l, close, vol) in enumerate(ohlcv):
            btc = Decimal(str(close))
            now = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

            # ── Manage existing positions ───────────────────────────────────
            still_open = []
            for pos in active_positions:
                time_left = (pos["expiry"] - now).total_seconds()

                if time_left <= 0:
                    # Resolution
                    is_win = (btc > pos["strike"] and pos["side"] == "YES") or \
                             (btc < pos["strike"] and pos["side"] == "NO")
                    pnl = Decimal("10") * (Decimal("1") - pos["entry"]) if is_win \
                          else Decimal("-10") * pos["entry"]
                    self.perf.record(pnl, pos["edge"], pos["side"], pos["title"])
                    continue

                cur_prob = self._calc_prob(btc, pos["strike"], time_left)
                cur_mp = cur_prob if pos["side"] == "YES" else (1 - cur_prob)
                sl = pos["entry"] * (1 - self.stop_loss_pct)
                tp = pos["entry"] + (1 - pos["entry"]) * self.take_profit_pct

                if cur_mp < sl:
                    pnl = Decimal("10") * (cur_mp - pos["entry"])
                    self.perf.record(pnl, pos["edge"], pos["side"] + "_SL", pos["title"])
                elif cur_mp > tp:
                    pnl = Decimal("10") * (cur_mp - pos["entry"])
                    self.perf.record(pnl, pos["edge"], pos["side"] + "_TP", pos["title"])
                else:
                    still_open.append(pos)
            active_positions = still_open

            # ── New opportunity every 5 candles ────────────────────────────
            if i % 5 == 0 and len(active_positions) < 5:
                strike = Decimal(str(round(float(btc) / 100) * 100))
                title = f"BTC {'Above' if btc >= strike else 'Below'} ${int(strike):,}"
                prob_yes = self._calc_prob(btc, strike, 300)
                price_yes = prob_yes - Decimal("0.05")
                price_no = (1 - prob_yes) - Decimal("0.05")
                edge_yes = prob_yes - price_yes
                edge_no = (1 - prob_yes) - price_no

                if edge_yes > self.edge_threshold:
                    active_positions.append({
                        "strike": strike, "side": "YES", "entry": price_yes,
                        "edge": edge_yes, "title": title,
                        "expiry": now + timedelta(seconds=300),
                    })
                elif edge_no > self.edge_threshold:
                    active_positions.append({
                        "strike": strike, "side": "NO", "entry": price_no,
                        "edge": edge_no, "title": title,
                        "expiry": now + timedelta(seconds=300),
                    })

        return self.perf


# ════════════════════════════════════════════════════════════════════════════
#  TRADING BOT
# ════════════════════════════════════════════════════════════════════════════
class TradingBot:
    def __init__(self):
        self.mode = os.getenv("TRADING_MODE", "DRY_RUN")
        self.edge_threshold = Decimal(os.getenv("EDGE_THRESHOLD", "0.10"))
        self.max_position_size = Decimal(os.getenv("MAX_POSITION_SIZE", "10.0"))
        self.stop_loss_pct = Decimal(os.getenv("STOP_LOSS_PCT", "0.05"))
        self.take_profit_pct = Decimal(os.getenv("TAKE_PROFIT_PCT", "0.15"))
        self.pnl_alert_threshold = Decimal(os.getenv("PNL_ALERT_THRESHOLD", "50.0"))  # USD
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_user_id = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

        # State
        self.is_paused = False
        self.active_markets: Dict = {}
        self.active_positions: Dict = {}
        self.btc_price = Decimal("0.0")
        self.dashboard_message_id: Optional[int] = None
        self.perf = PerformanceTracker()
        self._last_pnl_snapshot = Decimal("0.0")
        self._last_logs: List[str] = []

        # Clients
        self.clob_client = None
        self.binance = ccxt.binance()
        self.tg_app: Optional[Application] = None

    # ── Logging ──────────────────────────────────────────────────────────────
    def add_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._last_logs.append(entry)
        if len(self._last_logs) > 8:
            self._last_logs.pop(0)
        logger.info(msg)

    # ── Telegram helpers ─────────────────────────────────────────────────────
    def _esc(self, text: str) -> str:
        """Escape MarkdownV2 special chars."""
        for ch in r"\_*[]()~`>#+-=|{}.!":
            text = text.replace(ch, f"\\{ch}")
        return text

    async def _send(self, text: str, parse_mode: str = "MarkdownV2"):
        if not self.tg_app or not self.allowed_user_id:
            return
        try:
            await self.tg_app.bot.send_message(
                chat_id=self.allowed_user_id, text=text, parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    # ── Polymarket init ──────────────────────────────────────────────────────
    async def init_polymarket(self):
        try:
            if not ClobClient:
                self.add_log("py-clob-client not installed — simulating trades.")
                return False
            pk = os.getenv("POLYMARKET_PK")
            address = os.getenv("POLYMARKET_ADDRESS", "0xc7b9939135F5143D5b9eB968cf6f93566E31ff52")
            key = os.getenv("POLYMARKET_API_KEY")
            passphrase = os.getenv("POLYMARKET_API_PASSPHRASE")
            secret = os.getenv("POLYMARKET_API_SECRET")
            if not pk:
                self.add_log("POLYMARKET_PK not set — simulating trades.")
                return False
            creds = ApiCredential(key=key, passphrase=passphrase, secret=secret)
            self.clob_client = ClobClient(
                "https://clob.polymarket.com",
                key=pk, chain_id=POLYGON, funder=address, creds=creds,
            )
            self.add_log(f"Polymarket CLOB connected (addr: {address[:10]}…)")
            return True
        except Exception as e:
            self.add_log(f"Polymarket init failed: {e}")
            return False

    # ── Price feed ───────────────────────────────────────────────────────────
    async def price_feed_loop(self):
        while True:
            try:
                ticker = await self.binance.fetch_ticker("BTC/USDT")
                self.btc_price = Decimal(str(ticker["last"]))
                await asyncio.sleep(1)
            except Exception as e:
                self.add_log(f"Price feed error: {e}")
                await asyncio.sleep(5)

    # ── Market discovery ─────────────────────────────────────────────────────
    async def market_discovery_loop(self):
        while True:
            try:
                resp = requests.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"active": "true", "closed": "false", "query": "Bitcoin 5 minutes"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    markets = resp.json()
                    self.active_markets = {
                        m["id"]: m for m in markets
                        if "Bitcoin" in m.get("title", "") and "5 minutes" in m.get("title", "")
                    }
                    self.add_log(f"Discovered {len(self.active_markets)} active 5-min BTC markets.")
                await asyncio.sleep(60)
            except Exception as e:
                self.add_log(f"Market discovery error: {e}")
                await asyncio.sleep(30)

    # ── Trading loop ─────────────────────────────────────────────────────────
    async def trading_loop(self):
        while True:
            if self.is_paused:
                await asyncio.sleep(2)
                continue
            try:
                if self.active_markets:
                    await self._manage_positions()
                    await self._scan_for_entries()
                    await self._check_pnl_alerts()
            except Exception as e:
                self.add_log(f"Trading loop error: {e}")
            await asyncio.sleep(3)

    async def _calc_prob(self, btc: Decimal, strike: Decimal, time_left: float) -> Decimal:
        tf = Decimal(str(max(0.05, time_left / 300.0))).sqrt()
        z = (btc - strike) / (Decimal("100.0") * tf)
        p = Decimal("0.5") + (z / Decimal("2.0"))
        return max(Decimal("0.01"), min(Decimal("0.99"), p))

    async def _scan_for_entries(self):
        for market_id, market in self.active_markets.items():
            if market_id in self.active_positions:
                continue
            title = market.get("title", "")
            try:
                strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
                strike = Decimal(strike_str)
                expires_str = market.get("expires_at", "")
                if not expires_str:
                    continue
                expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                time_left = (expires - datetime.now(timezone.utc)).total_seconds()
                if time_left <= 0:
                    continue

                prob = await self._calc_prob(self.btc_price, strike, time_left)
                price_yes = prob - Decimal("0.05")
                price_no = (1 - prob) - Decimal("0.05")
                edge_yes = prob - price_yes
                edge_no = (1 - prob) - price_no

                if edge_yes > self.edge_threshold:
                    await self._enter(market_id, title, "YES", price_yes, edge_yes)
                elif edge_no > self.edge_threshold:
                    await self._enter(market_id, title, "NO", price_no, edge_no)
            except Exception as e:
                logger.debug(f"Entry scan error {market_id}: {e}")

    async def _enter(self, market_id: str, title: str, side: str, price: Decimal, edge: Decimal):
        self.add_log(f"ENTRY {side} | {title} | Edge {float(edge)*100:.1f}%")
        self.active_positions[market_id] = {
            "side": side, "size": self.max_position_size,
            "entry_price": price, "entry_btc": self.btc_price,
            "edge": edge, "title": title,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        escaped = self._esc(f"🚀 TRADE OPENED\n"
                            f"Market: {title}\n"
                            f"Side: {side}  |  Price: ${float(price):.3f}\n"
                            f"Edge: {float(edge)*100:.1f}%  |  Size: ${float(self.max_position_size)}")
        await self._send(escaped)

    async def _manage_positions(self):
        to_close = []
        for mid, pos in self.active_positions.items():
            market = self.active_markets.get(mid)
            if not market:
                to_close.append((mid, None, None))
                continue
            try:
                expires_str = market.get("expires_at", "")
                if not expires_str:
                    continue
                expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                time_left = (expires - datetime.now(timezone.utc)).total_seconds()

                if time_left <= 0:
                    strike_str = pos["title"].split("$")[1].split(" ")[0].replace(",", "")
                    strike = Decimal(strike_str)
                    is_win = (self.btc_price > strike and pos["side"] == "YES") or \
                             (self.btc_price < strike and pos["side"] == "NO")
                    pnl = pos["size"] * (Decimal("1") - pos["entry_price"]) if is_win \
                          else -pos["size"] * pos["entry_price"]
                    to_close.append((mid, pnl, "EXPIRED"))
                    continue

                prob = await self._calc_prob(self.btc_price, Decimal(pos["title"].split("$")[1].split(" ")[0].replace(",", "")), time_left)
                cur = prob if pos["side"] == "YES" else (1 - prob)
                sl = pos["entry_price"] * (1 - self.stop_loss_pct)
                tp = pos["entry_price"] + (1 - pos["entry_price"]) * self.take_profit_pct

                if cur < sl:
                    pnl = pos["size"] * (cur - pos["entry_price"])
                    to_close.append((mid, pnl, "SL"))
                elif cur > tp:
                    pnl = pos["size"] * (cur - pos["entry_price"])
                    to_close.append((mid, pnl, "TP"))
            except Exception as e:
                logger.debug(f"Manage position error {mid}: {e}")

        for mid, pnl, reason in to_close:
            pos = self.active_positions.pop(mid, None)
            if pos is None or pnl is None:
                continue
            self.perf.record(pnl, pos["edge"], pos["side"], pos["title"])
            icon = {"SL": "🛑", "TP": "🎯", "EXPIRED": "⏱️"}.get(reason, "✅")
            pnl_str = f"+${float(pnl):.2f}" if pnl >= 0 else f"-${abs(float(pnl)):.2f}"
            self.add_log(f"{reason} {pos['side']} | {pos['title']} | PnL {pnl_str}")
            escaped = self._esc(
                f"{icon} {reason}\n"
                f"Market: {pos['title']}\n"
                f"Side: {pos['side']}  |  PnL: {pnl_str}\n"
                f"Balance: ${float(self.perf.balance):.2f}"
            )
            await self._send(escaped)

    # ── P&L threshold alerts ─────────────────────────────────────────────────
    async def _check_pnl_alerts(self):
        current_pnl = self.perf.total_pnl
        delta = abs(current_pnl - self._last_pnl_snapshot)
        if delta >= self.pnl_alert_threshold:
            direction = "📈 PROFIT MILESTONE" if current_pnl > self._last_pnl_snapshot else "📉 DRAWDOWN ALERT"
            escaped = self._esc(
                f"{direction}\n"
                f"Cumulative P&L: ${float(current_pnl):.2f}\n"
                f"Change: ${float(current_pnl - self._last_pnl_snapshot):+.2f}\n"
                f"Win Rate: {self.perf.win_rate:.1f}%  |  Drawdown: {float(self.perf.max_drawdown):.1f}%"
            )
            await self._send(escaped)
            self._last_pnl_snapshot = current_pnl

    # ── Dashboard ────────────────────────────────────────────────────────────
    def _dashboard_text(self) -> str:
        status = "🟢 ACTIVE" if not self.is_paused else "🟡 PAUSED"
        mode = "🛑 LIVE" if self.mode == "LIVE" else "🧪 DRY\\-RUN"
        p = self.perf

        positions_block = ""
        for mid, pos in list(self.active_positions.items())[:3]:
            positions_block += f"├─ `{pos['side']}` {pos['title'][:20]}… @ `${float(pos['entry_price']):.3f}`\n"
        if len(self.active_positions) > 3:
            positions_block += f"└─ \\+{len(self.active_positions) - 3} more\n"
        if not self.active_positions:
            positions_block = "└─ _None_\n"

        logs_block = "\n".join(self._last_logs[-5:]) or "No activity yet."

        text = (
            f"🤖 *RECON HFT* \\| {status}\n"
            f"Mode: {mode} \\| BTC: `${float(self.btc_price):,.0f}`\n\n"
            f"📊 *Performance*\n"
            f"├─ Total P&L: `${float(p.total_pnl):+.2f}`\n"
            f"├─ Win Rate: `{p.win_rate:.1f}%` \\({p.wins}W / {p.losses}L\\)\n"
            f"├─ Trades: `{p.total_trades}`\n"
            f"├─ Balance: `${float(p.balance):.2f}`\n"
            f"└─ Drawdown: `{float(p.max_drawdown):.1f}%`\n\n"
            f"💼 *Open Positions* \\({len(self.active_positions)}\\)\n"
            f"{positions_block}\n"
            f"📋 *Recent Activity*\n"
            f"```\n{logs_block}\n```"
        )
        return text

    async def _refresh_dashboard(self, context: ContextTypes.DEFAULT_TYPE):
        while True:
            if self.dashboard_message_id and self.allowed_user_id:
                try:
                    keyboard = [
                        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                         InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle_pause")],
                        [InlineKeyboardButton("📊 Deep Stats", callback_data="deep_stats"),
                         InlineKeyboardButton("🏃 Backtest", callback_data="run_backtest")],
                    ]
                    await context.bot.edit_message_text(
                        chat_id=self.allowed_user_id,
                        message_id=self.dashboard_message_id,
                        text=self._dashboard_text(),
                        parse_mode="MarkdownV2",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                except Exception:
                    pass
            await asyncio.sleep(15)

    # ── Telegram commands ────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.allowed_user_id:
            await update.message.reply_text("⛔ Unauthorized.")
            return
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
             InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle_pause")],
            [InlineKeyboardButton("📊 Deep Stats", callback_data="deep_stats"),
             InlineKeyboardButton("🏃 Backtest", callback_data="run_backtest")],
        ]
        msg = await update.message.reply_text(
            self._dashboard_text(), parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        self.dashboard_message_id = msg.message_id
        asyncio.create_task(self._refresh_dashboard(context))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.allowed_user_id:
            return
        await update.message.reply_text(self._dashboard_text(), parse_mode="MarkdownV2")

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deep performance statistics."""
        if update.effective_user.id != self.allowed_user_id:
            return
        p = self.perf
        text = (
            f"📊 *DEEP PERFORMANCE STATS*\n\n"
            f"*Returns*\n"
            f"├─ Total P&L: `${float(p.total_pnl):+.2f}`\n"
            f"├─ ROI: `{p.roi:+.2f}%`\n"
            f"└─ Balance: `${float(p.balance):.2f}`\n\n"
            f"*Edge & Accuracy*\n"
            f"├─ Win Rate: `{p.win_rate:.1f}%`\n"
            f"├─ Wins / Losses: `{p.wins} / {p.losses}`\n"
            f"├─ Avg Profit: `${float(p.avg_profit):.3f}`\n"
            f"├─ Avg Loss: `${float(p.avg_loss):.3f}`\n"
            f"└─ Profit Factor: `{p.profit_factor:.2f}x`\n\n"
            f"*Risk*\n"
            f"├─ Max Drawdown: `{float(p.max_drawdown):.2f}%`\n"
            f"├─ Peak Balance: `${float(p.peak_balance):.2f}`\n"
            f"└─ Sharpe Ratio: `{p.sharpe_ratio:.2f}`\n\n"
            f"*Config*\n"
            f"├─ Edge Threshold: `{float(self.edge_threshold)*100:.0f}%`\n"
            f"├─ Stop Loss: `{float(self.stop_loss_pct)*100:.0f}%`\n"
            f"└─ Take Profit: `{float(self.take_profit_pct)*100:.0f}%`"
        )
        # Escape special chars
        for ch in ["+", "-", ".", "(", ")"]:
            text = text.replace(ch, f"\\{ch}")
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run backtester on last N candles of BTC/USDT 1m data."""
        if update.effective_user.id != self.allowed_user_id:
            return
        candles = 500
        if context.args:
            try:
                candles = max(50, min(2000, int(context.args[0])))
            except ValueError:
                pass

        await update.message.reply_text(f"⏳ Running backtest on last *{candles}* BTC/USDT 1m candles\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            bt = Backtester(
                edge_threshold=float(self.edge_threshold),
                stop_loss_pct=float(self.stop_loss_pct),
                take_profit_pct=float(self.take_profit_pct),
                candles=candles,
            )
            p = await bt.run()

            text = (
                f"📊 *BACKTEST RESULTS* \\({candles} candles\\)\n\n"
                f"*Returns*\n"
                f"├─ Total P&L: `${float(p.total_pnl):+.2f}`\n"
                f"├─ ROI: `{p.roi:+.2f}%`\n"
                f"└─ Final Balance: `${float(p.balance):.2f}`\n\n"
                f"*Accuracy*\n"
                f"├─ Trades: `{p.total_trades}`\n"
                f"├─ Win Rate: `{p.win_rate:.1f}%`\n"
                f"├─ Avg Profit: `${float(p.avg_profit):.3f}`\n"
                f"├─ Avg Loss: `${float(p.avg_loss):.3f}`\n"
                f"└─ Profit Factor: `{p.profit_factor:.2f}x`\n\n"
                f"*Risk*\n"
                f"├─ Max Drawdown: `{float(p.max_drawdown):.2f}%`\n"
                f"└─ Sharpe Ratio: `{p.sharpe_ratio:.2f}`\n\n"
                f"_Tip: Run `/backtest 1000` for a deeper simulation_"
            )
            for ch in ["+", "-", ".", "(", ")"]:
                text = text.replace(ch, f"\\{ch}")
            await update.message.reply_text(text, parse_mode="MarkdownV2")
        except Exception as e:
            await update.message.reply_text(f"❌ Backtest failed: {self._esc(str(e))}", parse_mode="MarkdownV2")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = True
        self.add_log("Bot paused by user.")
        await update.message.reply_text("🟡 Bot *PAUSED*\\.", parse_mode="MarkdownV2")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = False
        self.add_log("Bot resumed by user.")
        await update.message.reply_text("🟢 Bot *RESUMED*\\.", parse_mode="MarkdownV2")

    async def cmd_set_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            val = Decimal(context.args[0])
            self.edge_threshold = val
            await update.message.reply_text(f"✅ Edge threshold → `{float(val)*100:.1f}%`", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: `/setthreshold 0.10`", parse_mode="MarkdownV2")

    async def cmd_setalert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set P&L alert threshold in USD."""
        try:
            val = Decimal(context.args[0])
            self.pnl_alert_threshold = val
            await update.message.reply_text(f"🔔 P&L alert threshold → `${float(val):.0f}`", parse_mode="MarkdownV2")
        except Exception:
            await update.message.reply_text("❌ Usage: `/setalert 50` \\(USD\\)", parse_mode="MarkdownV2")

    # ── Callback buttons ─────────────────────────────────────────────────────
    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
             InlineKeyboardButton("⏸ Pause/Resume", callback_data="toggle_pause")],
            [InlineKeyboardButton("📊 Deep Stats", callback_data="deep_stats"),
             InlineKeyboardButton("🏃 Backtest", callback_data="run_backtest")],
        ]
        markup = InlineKeyboardMarkup(keyboard)

        if query.data == "refresh":
            await query.edit_message_text(self._dashboard_text(), parse_mode="MarkdownV2", reply_markup=markup)

        elif query.data == "toggle_pause":
            self.is_paused = not self.is_paused
            self.add_log(f"Bot {'PAUSED' if self.is_paused else 'RESUMED'} via dashboard.")
            await query.edit_message_text(self._dashboard_text(), parse_mode="MarkdownV2", reply_markup=markup)

        elif query.data == "deep_stats":
            await self.cmd_stats(update, context)

        elif query.data == "run_backtest":
            await query.message.reply_text("⏳ Running quick backtest \\(500 candles\\)\\.\\.\\.", parse_mode="MarkdownV2")
            try:
                bt = Backtester(
                    edge_threshold=float(self.edge_threshold),
                    stop_loss_pct=float(self.stop_loss_pct),
                    take_profit_pct=float(self.take_profit_pct),
                    candles=500,
                )
                p = await bt.run()
                result = (
                    f"📊 *Quick Backtest* \\(500 candles\\)\n"
                    f"P&L: `${float(p.total_pnl):+.2f}` \\| ROI: `{p.roi:+.1f}%`\n"
                    f"Win Rate: `{p.win_rate:.1f}%` \\({p.wins}W/{p.losses}L\\)\n"
                    f"Drawdown: `{float(p.max_drawdown):.1f}%` \\| Sharpe: `{p.sharpe_ratio:.2f}`"
                )
                for ch in ["+", "-", ".", "(", ")"]:
                    result = result.replace(ch, f"\\{ch}")
                await query.message.reply_text(result, parse_mode="MarkdownV2")
            except Exception as e:
                await query.message.reply_text(f"❌ Backtest error: {self._esc(str(e))}", parse_mode="MarkdownV2")

    # ── Start Telegram app ───────────────────────────────────────────────────
    async def start_telegram(self):
        if not self.telegram_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram disabled.")
            return
        self.tg_app = Application.builder().token(self.telegram_token).build()
        handlers = [
            ("start", self.cmd_start),
            ("status", self.cmd_status),
            ("stats", self.cmd_stats),
            ("backtest", self.cmd_backtest),
            ("pause", self.cmd_pause),
            ("resume", self.cmd_resume),
            ("setthreshold", self.cmd_set_threshold),
            ("setalert", self.cmd_setalert),
        ]
        for cmd, fn in handlers:
            self.tg_app.add_handler(CommandHandler(cmd, fn))
        self.tg_app.add_handler(CallbackQueryHandler(self.handle_callbacks))
        await self.tg_app.initialize()
        await self.tg_app.start()
        await self.tg_app.updater.start_polling()
        self.add_log("Telegram bot started.")


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════
async def main():
    bot = TradingBot()
    await bot.init_polymarket()
    tasks = [
        bot.price_feed_loop(),
        bot.market_discovery_loop(),
        bot.trading_loop(),
    ]
    if bot.telegram_token:
        tasks.append(bot.start_telegram())
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
