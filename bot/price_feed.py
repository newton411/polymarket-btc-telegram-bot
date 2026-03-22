"""
Multi-source real-time BTC price feed.
All providers are public REST APIs — no API key needed.

Priority order:
  1. Binance  — https://api.binance.com  (lowest latency, highest reliability)
  2. Kraken   — https://api.kraken.com
  3. CoinGecko — https://api.coingecko.com  (rate-limited but always up)
  4. CoinCap  — https://api.coincap.io   (generous free tier)

Also provides:
  - Rolling sigma (annualised volatility proxy in USD) for strategy Z-score calc
  - 24-hour stats (change, high, low, volume) from Binance
"""
import asyncio
import logging
import math
import time
from collections import deque
from decimal import Decimal
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Public price endpoints ─────────────────────────────────────────────────────
_BINANCE_PRICE   = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
_BINANCE_24H     = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
_KRAKEN_TICKER   = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
_COINGECKO_URL   = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
_COINCAP_URL     = "https://api.coincap.io/v2/assets/bitcoin"


class PriceFeed:
    """
    Async, multi-source BTC/USD price feed.

    Keeps a rolling 60-tick history to compute σ (annualised vol in USD),
    which drives the Bayesian Z-score strategy in strategies.py.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_price: Decimal = Decimal("0")
        self.last_update: float = 0.0
        self._cache_ttl: float = 1.0   # 1-second cache to avoid hammering APIs

        # Rolling returns (last 60 ticks ≈ 1 minute at 1s polling)
        self._returns: deque = deque(maxlen=60)
        self.sigma: Decimal = Decimal("100")   # initial σ in USD

        # 24-hour stats (refreshed periodically)
        self.change_24h_pct: float = 0.0
        self.high_24h: Decimal = Decimal("0")
        self.low_24h: Decimal = Decimal("0")
        self.volume_24h_usd: Decimal = Decimal("0")
        self._last_24h_refresh: float = 0.0

    # ── Session ───────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
                headers={"User-Agent": "RecondTrade/2.0"},
            )
        return self._session

    # ── Per-provider fetchers ─────────────────────────────────────────────────

    async def _binance(self) -> Decimal:
        s = await self._get_session()
        async with s.get(_BINANCE_PRICE) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["price"]))

    async def _kraken(self) -> Decimal:
        s = await self._get_session()
        async with s.get(_KRAKEN_TICKER) as r:
            r.raise_for_status()
            data = await r.json()
            pair_data = list(data["result"].values())[0]
            return Decimal(str(pair_data["c"][0]))   # "c" = [last_price, lot_volume]

    async def _coingecko(self) -> Decimal:
        s = await self._get_session()
        async with s.get(_COINGECKO_URL) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["bitcoin"]["usd"]))

    async def _coincap(self) -> Decimal:
        s = await self._get_session()
        async with s.get(_COINCAP_URL) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["data"]["priceUsd"]))

    # ── Main price getter ─────────────────────────────────────────────────────

    async def get_btc_price(self) -> Decimal:
        """
        Return BTC/USD price from the fastest available source.
        Uses a 1-second cache; falls back through providers on error.
        """
        now = time.time()
        if self.last_price > 0 and (now - self.last_update) < self._cache_ttl:
            return self.last_price

        # Refresh 24h stats every 60 seconds
        if now - self._last_24h_refresh > 60:
            asyncio.ensure_future(self._refresh_24h())

        providers = [
            ("Binance",   self._binance),
            ("Kraken",    self._kraken),
            ("CoinGecko", self._coingecko),
            ("CoinCap",   self._coincap),
        ]

        for name, fn in providers:
            try:
                price = await fn()
                if price > 0:
                    self._record(price)
                    if name != "Binance":
                        logger.debug(f"Price feed: using {name} fallback (${float(price):,.2f})")
                    self.last_update = now
                    return self.last_price
            except Exception as e:
                logger.debug(f"{name} price feed error: {e}")

        # All failed — return stale price
        if self.last_price > 0:
            logger.warning(f"All price feeds failed — using stale ${float(self.last_price):,.2f}")
            return self.last_price

        raise RuntimeError("All BTC price feeds failed and no stale data available")

    async def _refresh_24h(self):
        """Fetch Binance 24h stats in the background."""
        try:
            s = await self._get_session()
            async with s.get(_BINANCE_24H) as r:
                r.raise_for_status()
                d = await r.json()
                self.change_24h_pct = float(d.get("priceChangePercent", 0))
                self.high_24h = Decimal(str(d.get("highPrice", "0")))
                self.low_24h = Decimal(str(d.get("lowPrice", "0")))
                self.volume_24h_usd = Decimal(str(d.get("quoteVolume", "0")))
                self._last_24h_refresh = time.time()
                logger.debug(f"24h stats refreshed: change={self.change_24h_pct:+.2f}%")
        except Exception as e:
            logger.debug(f"24h stats refresh failed: {e}")

    def _record(self, price: Decimal):
        """Update sigma from rolling returns and store price."""
        if self.last_price > 0 and self.last_price != price:
            ret = float((price - self.last_price) / self.last_price)
            self._returns.append(ret)
            if len(self._returns) >= 2:
                n = len(self._returns)
                mean = sum(self._returns) / n
                var = sum((x - mean) ** 2 for x in self._returns) / n
                std = math.sqrt(max(var, 1e-12))
                # Annualise: √(60s × 24h × 365d) = √(31_536_000)
                ann_std = std * math.sqrt(31_536_000)
                self.sigma = Decimal(str(float(price) * ann_std))
        self.last_price = price

    # ── Stats dict ────────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return {
            "price":        float(self.last_price),
            "sigma_usd":    float(self.sigma),
            "change_24h":   self.change_24h_pct,
            "high_24h":     float(self.high_24h),
            "low_24h":      float(self.low_24h),
            "volume_24h":   float(self.volume_24h_usd),
            "last_update":  self.last_update,
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
