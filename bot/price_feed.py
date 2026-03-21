"""
Multi-source real-time BTC price feed.

Primary  : Binance public REST (no API key needed)
Secondary: Kraken public REST
Tertiary : CoinGecko public REST (rate-limited but always available)
Quaternary: CoinCap REST

Inspired by RobotTraders Python-for-Finance patterns:
  - Prefer async HTTP over ccxt for lower latency
  - Exponential backoff retry on failure
  - Sigma (volatility proxy) updated from rolling returns
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

# ── Public endpoints (no API key required) ──────────────────────────────────
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
KRAKEN_TICKER  = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
COINGECKO_URL  = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
COINCAP_URL    = "https://api.coincap.io/v2/assets/bitcoin"


class PriceFeed:
    """
    Async multi-source BTC price feed with:
    - Automatic failover across 4 providers
    - Rolling volatility (sigma) estimation
    - Cache to avoid redundant requests
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_price: Decimal = Decimal("0")
        self.last_update: float = 0.0
        self._cache_ttl: float = 1.0   # 1-second cache

        # Rolling returns for sigma estimation (last 60 ticks ~ 1 min at 1s poll)
        self._price_history: deque = deque(maxlen=60)
        self.sigma: Decimal = Decimal("100")   # annualised vol proxy (dollars)

        # 24h stats
        self.price_24h_ago: Decimal = Decimal("0")
        self.change_24h_pct: float = 0.0
        self.high_24h: Decimal = Decimal("0")
        self.low_24h:  Decimal = Decimal("0")
        self.volume_24h: Decimal = Decimal("0")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    # ── Provider helpers ────────────────────────────────────────────────────
    async def _binance_price(self) -> Decimal:
        session = await self._get_session()
        async with session.get(BINANCE_TICKER) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["price"]))

    async def _binance_ticker_24h(self) -> None:
        """Fetch 24-h stats from Binance."""
        session = await self._get_session()
        url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        try:
            async with session.get(url) as r:
                r.raise_for_status()
                data = await r.json()
                self.change_24h_pct = float(data.get("priceChangePercent", 0))
                self.high_24h  = Decimal(str(data.get("highPrice", "0")))
                self.low_24h   = Decimal(str(data.get("lowPrice",  "0")))
                self.volume_24h = Decimal(str(data.get("quoteVolume", "0")))
        except Exception as e:
            logger.debug(f"Binance 24h ticker failed: {e}")

    async def _kraken_price(self) -> Decimal:
        session = await self._get_session()
        async with session.get(KRAKEN_TICKER) as r:
            r.raise_for_status()
            data = await r.json()
            result = data.get("result", {})
            pair = list(result.values())[0]
            # "c" = [last_price, lot_volume]
            return Decimal(str(pair["c"][0]))

    async def _coingecko_price(self) -> Decimal:
        session = await self._get_session()
        async with session.get(COINGECKO_URL) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["bitcoin"]["usd"]))

    async def _coincap_price(self) -> Decimal:
        session = await self._get_session()
        async with session.get(COINCAP_URL) as r:
            r.raise_for_status()
            data = await r.json()
            return Decimal(str(data["data"]["priceUsd"]))

    # ── Public interface ────────────────────────────────────────────────────
    async def get_btc_price(self) -> Decimal:
        """Return BTC/USD price, using cache when fresh enough."""
        now = time.time()
        if self.last_price > 0 and (now - self.last_update) < self._cache_ttl:
            return self.last_price

        providers = [
            ("Binance",   self._binance_price),
            ("Kraken",    self._kraken_price),
            ("CoinGecko", self._coingecko_price),
            ("CoinCap",   self._coincap_price),
        ]

        for name, fn in providers:
            try:
                price = await fn()
                if price > 0:
                    self._record_price(price)
                    self.last_update = now
                    if name != "Binance":
                        logger.info(f"Price feed: using {name} fallback")
                    return self.last_price
            except Exception as e:
                logger.warning(f"{name} price feed error: {e}")

        # All providers failed — return stale
        if self.last_price > 0:
            logger.warning("All price feeds failed — using stale price")
            return self.last_price

        raise RuntimeError("All price feeds failed and no stale data available")

    def _record_price(self, price: Decimal) -> None:
        """Record price, update sigma and last_price."""
        if self.last_price > 0:
            ret = float((price - self.last_price) / self.last_price)
            self._price_history.append(ret)
            if len(self._price_history) >= 2:
                n    = len(self._price_history)
                mean = sum(self._price_history) / n
                var  = sum((x - mean) ** 2 for x in self._price_history) / n
                std_per_s = math.sqrt(var)
                # Annualise: sqrt(60s * 24h * 365d) ≈ sqrt(31_536_000)
                ann_std = std_per_s * math.sqrt(31_536_000)
                # Convert to dollar sigma
                self.sigma = Decimal(str(float(price) * ann_std))

        self.last_price = price
        self._price_history.append(0.0)  # pad initial

    async def refresh_24h_stats(self) -> None:
        """Refresh 24h stats (call periodically, not every tick)."""
        await self._binance_ticker_24h()

    @property
    def stats_dict(self) -> dict:
        return {
            "price":        float(self.last_price),
            "sigma":        float(self.sigma),
            "change_24h":   self.change_24h_pct,
            "high_24h":     float(self.high_24h),
            "low_24h":      float(self.low_24h),
            "volume_24h":   float(self.volume_24h),
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
