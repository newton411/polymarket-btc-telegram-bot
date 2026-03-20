"""
RECON HFT – Backtesting Module
Simulates the Bayesian Z-Score strategy against real historical BTC OHLCV data.

Usage (standalone):
    python -m bot.backtest --limit 2000 --edge 0.10 --sl 0.05 --tp 0.15

Usage (from main.py /backtest command):
    backtester = Backtester(limit=1500)
    await backtester.run()
    results = backtester.get_report()
"""

import asyncio
import argparse
import logging
import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


class TradeRecord:
    __slots__ = ("entry_time", "exit_time", "side", "strike", "entry_price",
                 "exit_price", "size", "pnl", "exit_reason")

    def __init__(self, entry_time, side, strike, entry_price, size):
        self.entry_time  = entry_time
        self.exit_time   = None
        self.side        = side
        self.strike      = strike
        self.entry_price = entry_price
        self.exit_price  = Decimal("0")
        self.size        = size
        self.pnl         = Decimal("0")
        self.exit_reason = ""


class Backtester:
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1m",
        limit: int = 1500,
        edge_threshold: float = 0.10,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        position_size: float = 10.0,
        initial_balance: float = 1000.0,
    ):
        self.symbol         = symbol
        self.timeframe      = timeframe
        self.limit          = limit
        self.edge_threshold = Decimal(str(edge_threshold))
        self.stop_loss_pct  = Decimal(str(stop_loss_pct))
        self.take_profit_pct = Decimal(str(take_profit_pct))
        self.position_size  = Decimal(str(position_size))
        self.initial_balance = Decimal(str(initial_balance))

        # Internal state
        self.balance        = self.initial_balance
        self.trades: List[TradeRecord] = []
        self.equity_curve: List[float] = [float(self.initial_balance)]
        self.sigma_proxy    = Decimal("100.0")

        # Results populated after run()
        self.report: Optional[Dict] = None

    # ─────────────────────────────────────────────────────────────────────
    #  DATA FETCHING
    # ─────────────────────────────────────────────────────────────────────
    async def _fetch_ohlcv(self) -> List:
        exchange = ccxt.binance({"enableRateLimit": True})
        try:
            logger.info(f"Fetching {self.limit} × {self.timeframe} candles for {self.symbol}…")
            bars = await exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=self.limit)
            return bars
        finally:
            await exchange.close()

    # ─────────────────────────────────────────────────────────────────────
    #  STRATEGY HELPERS
    # ─────────────────────────────────────────────────────────────────────
    def _calc_prob(self, btc_price: Decimal, strike: Decimal, time_left_s: float) -> Decimal:
        """Bayesian implied probability via linear-CDF approximation."""
        clamped = max(0.1, time_left_s / 300.0)
        time_factor = Decimal(str(math.sqrt(clamped)))
        z = (btc_price - strike) / (self.sigma_proxy * time_factor)
        p = Decimal("0.5") + (z / Decimal("2.0"))
        return max(Decimal("0.01"), min(Decimal("0.99"), p))

    def _round_strike(self, price: Decimal) -> Decimal:
        """Snap to nearest $50 – mimics real Polymarket market creation."""
        return Decimal(str(round(float(price) / 50) * 50))

    # ─────────────────────────────────────────────────────────────────────
    #  MAIN SIMULATION
    # ─────────────────────────────────────────────────────────────────────
    async def run(self):
        bars = await self._fetch_ohlcv()
        if not bars:
            raise RuntimeError("No historical data returned from exchange.")

        active: List[TradeRecord] = []

        for idx, bar in enumerate(bars):
            ts, _, high, low, close, _ = bar
            now       = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            btc_price = Decimal(str(close))

            # ── 1. Manage open positions (SL / TP / expiry) ──────────────
            closed_this_bar = []
            for pos in active:
                elapsed    = (now - pos.entry_time).total_seconds()
                time_left  = max(0.0, 300.0 - elapsed)

                # Market expired → resolve at settlement
                if time_left <= 0:
                    is_win = (
                        (btc_price > pos.strike and pos.side == "YES") or
                        (btc_price < pos.strike and pos.side == "NO")
                    )
                    pos.exit_price  = Decimal("1.0") if is_win else Decimal("0.0")
                    pos.pnl         = pos.size * (pos.exit_price - pos.entry_price)
                    pos.exit_reason = "EXPIRY_WIN" if is_win else "EXPIRY_LOSS"
                    pos.exit_time   = now
                    closed_this_bar.append(pos)
                    continue

                # Current market price proxy
                curr_prob = self._calc_prob(btc_price, pos.strike, time_left)
                mkt_price = curr_prob if pos.side == "YES" else (1 - curr_prob)

                sl_price = pos.entry_price * (1 - self.stop_loss_pct)
                tp_price = pos.entry_price + (1 - pos.entry_price) * self.take_profit_pct

                if mkt_price <= sl_price:
                    pos.exit_price  = mkt_price
                    pos.pnl         = pos.size * (mkt_price - pos.entry_price)
                    pos.exit_reason = "STOP_LOSS"
                    pos.exit_time   = now
                    closed_this_bar.append(pos)
                elif mkt_price >= tp_price:
                    pos.exit_price  = mkt_price
                    pos.pnl         = pos.size * (mkt_price - pos.entry_price)
                    pos.exit_reason = "TAKE_PROFIT"
                    pos.exit_time   = now
                    closed_this_bar.append(pos)

            for p in closed_this_bar:
                active.remove(p)
                self.trades.append(p)
                self.balance += p.pnl
                self.equity_curve.append(float(self.balance))

            # ── 2. Entry scan every 5th bar (one new 5-min market) ────────
            if idx % 5 == 0:
                strike = self._round_strike(btc_price)
                prob_y = self._calc_prob(btc_price, strike, 300.0)
                spread = Decimal("0.04")

                price_yes = prob_y - spread / 2
                price_no  = (1 - prob_y) - spread / 2

                edge_yes = prob_y - price_yes
                edge_no  = (1 - prob_y) - price_no

                if edge_yes >= self.edge_threshold and len(active) < 5:
                    pos = TradeRecord(now, "YES", strike, price_yes, self.position_size)
                    active.append(pos)
                elif edge_no >= self.edge_threshold and len(active) < 5:
                    pos = TradeRecord(now, "NO", strike, price_no, self.position_size)
                    active.append(pos)

        self._build_report()

    # ─────────────────────────────────────────────────────────────────────
    #  STATISTICS
    # ─────────────────────────────────────────────────────────────────────
    def _build_report(self):
        trades = self.trades
        n      = len(trades)

        if n == 0:
            self.report = {"error": "No trades generated – lower edge threshold?"}
            return

        wins   = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        total_pnl    = sum(t.pnl for t in trades)
        avg_win      = sum(t.pnl for t in wins) / len(wins) if wins else Decimal("0")
        avg_loss     = sum(t.pnl for t in losses) / len(losses) if losses else Decimal("0")
        win_rate     = len(wins) / n * 100
        profit_factor = (
            abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses))
            if losses and sum(t.pnl for t in losses) != 0
            else float("inf")
        )

        # Max drawdown
        peak    = self.equity_curve[0]
        max_dd  = 0.0
        for v in self.equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (assumes risk-free ≈ 0, per-trade returns)
        pnl_list = [float(t.pnl) for t in trades]
        mean_r   = sum(pnl_list) / n
        var_r    = sum((x - mean_r) ** 2 for x in pnl_list) / n
        std_r    = math.sqrt(var_r) if var_r > 0 else 1e-9
        sharpe   = (mean_r / std_r) * math.sqrt(252 * 288)  # annualised, 5-min bars

        # Exit breakdown
        by_exit: Dict[str, int] = {}
        for t in trades:
            by_exit[t.exit_reason] = by_exit.get(t.exit_reason, 0) + 1

        roi = float(total_pnl / self.initial_balance * 100)

        self.report = {
            "symbol":          self.symbol,
            "bars_analysed":   self.limit,
            "total_trades":    n,
            "win_rate":        round(win_rate, 2),
            "profit_factor":   round(float(profit_factor), 3),
            "total_pnl":       float(total_pnl.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "roi_pct":         round(roi, 2),
            "avg_win":         float(avg_win.quantize(Decimal("0.0001"))),
            "avg_loss":        float(avg_loss.quantize(Decimal("0.0001"))),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "sharpe_ratio":    round(sharpe, 3),
            "initial_balance": float(self.initial_balance),
            "final_balance":   float(self.balance.quantize(Decimal("0.01"))),
            "exit_breakdown":  by_exit,
        }

    # ─────────────────────────────────────────────────────────────────────
    #  FORMATTED REPORT STRINGS
    # ─────────────────────────────────────────────────────────────────────
    def format_telegram_report(self) -> str:
        r = self.report
        if not r or "error" in r:
            return f"❌ Backtest failed: {r.get('error', 'unknown')}"

        pnl_sign = "📈" if r["total_pnl"] >= 0 else "📉"
        exit_str  = "  ".join(f"`{k}` × {v}" for k, v in r["exit_breakdown"].items())

        lines = [
            "📊 *BACKTEST RESULTS*",
            f"_Strategy: Bayesian Z\\-Score v2 \\| {r['bars_analysed']} × 1m bars_",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "💰 *P&L Summary*",
            f"├─ Start Balance: `${r['initial_balance']:,.2f}`",
            f"├─ End Balance:   `${r['final_balance']:,.2f}`",
            f"├─ {pnl_sign} Total P&L:  `${r['total_pnl']:+.2f}`",
            f"└─ ROI:           `{r['roi_pct']:+.2f}%`",
            "",
            "📈 *Trade Statistics*",
            f"├─ Total Trades:  `{r['total_trades']}`",
            f"├─ Win Rate:      `{r['win_rate']:.1f}%`",
            f"├─ Profit Factor: `{r['profit_factor']:.3f}`",
            f"├─ Avg Win:       `${r['avg_win']:+.4f}`",
            f"└─ Avg Loss:      `${r['avg_loss']:+.4f}`",
            "",
            "⚠️ *Risk Metrics*",
            f"├─ Max Drawdown:  `{r['max_drawdown_pct']:.2f}%`",
            f"└─ Sharpe Ratio:  `{r['sharpe_ratio']:.3f}`",
            "",
            "🔑 *Exit Breakdown*",
            f"`{exit_str}`",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)

    def print_report(self):
        r = self.report
        if not r or "error" in r:
            print(f"ERROR: {r.get('error', 'unknown')}")
            return
        print("\n" + "=" * 50)
        print("  RECON HFT — BACKTEST REPORT")
        print("=" * 50)
        for k, v in r.items():
            print(f"  {k:<22} {v}")
        print("=" * 50 + "\n")


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RECON HFT Backtest")
    parser.add_argument("--limit",  type=int,   default=1500,  help="Number of 1m candles")
    parser.add_argument("--edge",   type=float, default=0.10,  help="Min edge threshold")
    parser.add_argument("--sl",     type=float, default=0.05,  help="Stop-loss %")
    parser.add_argument("--tp",     type=float, default=0.15,  help="Take-profit %")
    parser.add_argument("--size",   type=float, default=10.0,  help="Position size USDC")
    parser.add_argument("--bal",    type=float, default=1000.0, help="Starting balance")
    args = parser.parse_args()

    bt = Backtester(
        limit=args.limit,
        edge_threshold=args.edge,
        stop_loss_pct=args.sl,
        take_profit_pct=args.tp,
        position_size=args.size,
        initial_balance=args.bal,
    )
    asyncio.run(bt.run())
    bt.print_report()
