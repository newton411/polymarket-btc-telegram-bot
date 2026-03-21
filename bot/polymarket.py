"""
Polymarket API integration — real-time Gamma API + CLOB
Inspired by RobotTraders/bits_and_bobs patterns:
  https://github.com/RobotTraders/bits_and_bobs/blob/main/polymarket_python.ipynb

Key endpoints used:
  Gamma API  : https://gamma-api.polymarket.com/markets
  CLOB API   : https://clob.polymarket.com
  Strapi API : https://polymarket-api.polymarket.com/markets  (extra metadata)
"""
import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# ─── Gamma API ─────────────────────────────────────────────────────────────
GAMMA_API  = "https://gamma-api.polymarket.com"
CLOB_API   = "https://clob.polymarket.com"
STRAPI_API = "https://polymarket-api.polymarket.com"


@dataclass
class TokenInfo:
    token_id: str
    outcome: str          # "Yes" or "No"
    price: Decimal = Decimal("0.5")
    winner: bool = False


@dataclass
class MarketInfo:
    """Rich market information from Gamma API."""
    market_id: str        # slug / conditionId
    question: str
    active: bool
    closed: bool
    end_date_iso: str
    volume: Decimal
    volume_24hr: Decimal
    outcomes: List[str]
    prices: List[Decimal]
    tokens: List[TokenInfo] = field(default_factory=list)
    # Extra fields from Gamma
    liquidity: Decimal = Decimal("0")
    spread: Decimal = Decimal("0")
    last_trade_price: Decimal = Decimal("0")

    @property
    def yes_price(self) -> Decimal:
        return self.prices[0] if self.prices else Decimal("0.5")

    @property
    def no_price(self) -> Decimal:
        return self.prices[1] if len(self.prices) > 1 else Decimal("0.5")

    @property
    def implied_prob_yes(self) -> Decimal:
        total = self.yes_price + self.no_price
        if total <= 0:
            return Decimal("0.5")
        return self.yes_price / total


@dataclass
class OrderBook:
    """Full CLOB order book snapshot."""
    market_id: str
    token_id: str
    yes_asks: List[Tuple[Decimal, Decimal]] = field(default_factory=list)
    yes_bids: List[Tuple[Decimal, Decimal]] = field(default_factory=list)
    no_asks: List[Tuple[Decimal, Decimal]]  = field(default_factory=list)
    no_bids: List[Tuple[Decimal, Decimal]]  = field(default_factory=list)
    timestamp: float = 0.0
    mid_price: Decimal = Decimal("0.5")
    spread_pct: Decimal = Decimal("0")

    def best_ask(self) -> Optional[Decimal]:
        return min(self.yes_asks, key=lambda x: x[0])[0] if self.yes_asks else None

    def best_bid(self) -> Optional[Decimal]:
        return max(self.yes_bids, key=lambda x: x[0])[0] if self.yes_bids else None


class PolymarketClient:
    """
    Async Polymarket API client.
    Uses aiohttp session for all HTTP — no blocking calls.

    Pattern from RobotTraders notebook:
      1. List markets via Gamma API (no auth needed)
      2. Fetch order books via CLOB API
      3. Place orders via py-clob-client (optional, live only)
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.clob_client = None   # set by TradingBot.init_polymarket()
        self._market_cache: Dict[str, MarketInfo] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 30.0  # seconds

    # ── Session management ──────────────────────────────────────────────────
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": "RECON-HFT/2.0 (Polymarket BTC Bot)",
                "Accept": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Gamma API helpers ───────────────────────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=5))
    async def _gamma_get(self, path: str, params: Optional[Dict] = None) -> dict:
        session = await self._get_session()
        url = f"{GAMMA_API}{path}"
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=1, max=5))
    async def _clob_get(self, path: str, params: Optional[Dict] = None) -> dict:
        session = await self._get_session()
        url = f"{CLOB_API}{path}"
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ── Market discovery ────────────────────────────────────────────────────
    async def discover_btc_markets(self) -> List[MarketInfo]:
        """
        Discover active BTC 5-minute Up/Down markets.
        Uses the exact Gamma API query pattern from RobotTraders notebook.
        """
        now = time.time()
        if self._market_cache and (now - self._cache_ts) < self._cache_ttl:
            return list(self._market_cache.values())

        markets: List[MarketInfo] = []
        params = {
            "active":  "true",
            "closed":  "false",
            "limit":   "100",
            "order":   "volume24hr",
            "ascending": "false",
        }
        try:
            data = await self._gamma_get("/markets", params)
            raw_markets = data if isinstance(data, list) else data.get("markets", [])

            for m in raw_markets:
                question = m.get("question", "") or m.get("title", "") or ""
                # Filter for BTC 5-minute binary markets
                q_lower = question.lower()
                if not (("bitcoin" in q_lower or "btc" in q_lower) and
                        ("5" in q_lower or "five" in q_lower) and
                        ("minute" in q_lower or "min" in q_lower)):
                    continue

                outcomes_raw = m.get("outcomes", "[]")
                if isinstance(outcomes_raw, str):
                    import json as _json
                    try:
                        outcomes = _json.loads(outcomes_raw)
                    except Exception:
                        outcomes = []
                else:
                    outcomes = outcomes_raw or []

                prices_raw = m.get("outcomePrices", "[]")
                if isinstance(prices_raw, str):
                    import json as _json
                    try:
                        prices_raw = _json.loads(prices_raw)
                    except Exception:
                        prices_raw = []

                prices = []
                for p in prices_raw:
                    try:
                        prices.append(Decimal(str(p)))
                    except Exception:
                        prices.append(Decimal("0.5"))

                # Build token list
                tokens_raw = m.get("tokens", [])
                tokens = []
                for t in tokens_raw:
                    tokens.append(TokenInfo(
                        token_id=t.get("token_id", ""),
                        outcome=t.get("outcome", ""),
                        price=Decimal(str(t.get("price", "0.5"))),
                        winner=t.get("winner", False),
                    ))

                mi = MarketInfo(
                    market_id=m.get("conditionId") or m.get("id", ""),
                    question=question,
                    active=m.get("active", False),
                    closed=m.get("closed", False),
                    end_date_iso=m.get("endDateIso") or m.get("endDate", ""),
                    volume=Decimal(str(m.get("volume") or "0")),
                    volume_24hr=Decimal(str(m.get("volume24hr") or "0")),
                    outcomes=outcomes,
                    prices=prices,
                    tokens=tokens,
                    liquidity=Decimal(str(m.get("liquidity") or "0")),
                    last_trade_price=Decimal(str(m.get("lastTradePrice") or "0")),
                )
                markets.append(mi)

            logger.info(f"Discovered {len(markets)} BTC 5-min markets via Gamma API")
            self._market_cache = {m.market_id: m for m in markets}
            self._cache_ts = now
        except Exception as e:
            logger.error(f"Gamma market discovery failed: {e}")
            # Return stale cache if available
            if self._market_cache:
                logger.warning("Returning stale market cache")
                return list(self._market_cache.values())

        return markets

    async def get_all_markets_raw(self, limit: int = 200) -> List[dict]:
        """
        Fetch raw market list — used for scanning all active markets.
        Mirrors the RobotTraders notebook: `requests.get(GAMMA_URL, params={...})`
        """
        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": str(limit),
                "order": "volume24hr",
                "ascending": "false",
            }
            data = await self._gamma_get("/markets", params)
            return data if isinstance(data, list) else data.get("markets", [])
        except Exception as e:
            logger.error(f"Raw market fetch failed: {e}")
            return []

    async def get_market_by_slug(self, slug: str) -> Optional[dict]:
        """Fetch a single market by slug."""
        try:
            data = await self._gamma_get(f"/markets", {"slug": slug})
            markets = data if isinstance(data, list) else data.get("markets", [])
            return markets[0] if markets else None
        except Exception as e:
            logger.error(f"Market by slug failed: {e}")
            return None

    # ── CLOB order book ─────────────────────────────────────────────────────
    async def get_orderbook(self, token_id: str) -> Optional[OrderBook]:
        """
        Fetch live CLOB order book for a token.
        CLOB endpoint: GET /book?token_id=<token_id>
        Response: { "bids": [{"price":..,"size":..}], "asks": [...] }
        """
        try:
            data = await self._clob_get("/book", {"token_id": token_id})
            raw_bids = data.get("bids", [])
            raw_asks = data.get("asks", [])

            yes_bids = [(Decimal(str(b["price"])), Decimal(str(b["size"]))) for b in raw_bids]
            yes_asks = [(Decimal(str(a["price"])), Decimal(str(a["size"]))) for a in raw_asks]

            # NO side = complement prices
            no_bids = [(Decimal("1") - p, s) for p, s in yes_asks]
            no_asks = [(Decimal("1") - p, s) for p, s in yes_bids]

            mid = Decimal("0.5")
            if yes_bids and yes_asks:
                best_bid = max(yes_bids, key=lambda x: x[0])[0]
                best_ask = min(yes_asks, key=lambda x: x[0])[0]
                mid = (best_bid + best_ask) / 2

            ob = OrderBook(
                market_id=token_id,
                token_id=token_id,
                yes_asks=yes_asks,
                yes_bids=yes_bids,
                no_asks=no_asks,
                no_bids=no_bids,
                timestamp=time.time(),
                mid_price=mid,
            )
            if yes_bids and yes_asks:
                ob.spread_pct = (min(yes_asks, key=lambda x: x[0])[0] -
                                 max(yes_bids, key=lambda x: x[0])[0])
            return ob

        except Exception as e:
            logger.warning(f"CLOB orderbook fetch failed for {token_id}: {e}")
            return self._simulated_orderbook(token_id)

    def _simulated_orderbook(self, token_id: str) -> OrderBook:
        """Realistic simulated order book for dry-run / when CLOB is unavailable."""
        import random
        mid = Decimal("0.5") + Decimal(str(round(random.uniform(-0.15, 0.15), 3)))
        spread = Decimal("0.015")
        levels = 5
        yes_asks = [
            (mid + spread + Decimal(str(i * 0.01)), Decimal(str(round(random.uniform(20, 200), 2))))
            for i in range(levels)
        ]
        yes_bids = [
            (mid - spread - Decimal(str(i * 0.01)), Decimal(str(round(random.uniform(20, 200), 2))))
            for i in range(levels)
        ]
        no_bids = [(Decimal("1") - p, s) for p, s in yes_asks]
        no_asks = [(Decimal("1") - p, s) for p, s in yes_bids]
        return OrderBook(
            market_id=token_id,
            token_id=token_id,
            yes_asks=yes_asks,
            yes_bids=yes_bids,
            no_asks=no_asks,
            no_bids=no_bids,
            timestamp=time.time(),
            mid_price=mid,
            spread_pct=spread * 2,
        )

    # ── Best prices ─────────────────────────────────────────────────────────
    def get_best_prices(self, ob: OrderBook
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Extract best bid/ask for YES and NO sides."""
        best_yes_bid = max(ob.yes_bids, key=lambda x: x[0])[0] if ob.yes_bids else None
        best_yes_ask = min(ob.yes_asks, key=lambda x: x[0])[0] if ob.yes_asks else None
        best_no_bid  = max(ob.no_bids,  key=lambda x: x[0])[0] if ob.no_bids  else None
        best_no_ask  = min(ob.no_asks,  key=lambda x: x[0])[0] if ob.no_asks  else None
        return best_yes_bid, best_yes_ask, best_no_bid, best_no_ask

    # ── Real-time market prices (lightweight) ───────────────────────────────
    async def get_market_prices(self, token_ids: List[str]) -> Dict[str, Decimal]:
        """
        Batch-fetch current mid prices for a list of token IDs.
        Uses CLOB /prices endpoint for efficiency.
        """
        if not token_ids:
            return {}
        try:
            # CLOB supports comma-separated token_ids
            params = {"token_id": ",".join(token_ids[:20])}  # limit to 20
            data = await self._clob_get("/prices", params)
            # Response: {"0xabc...": "0.62", ...}
            return {
                tid: Decimal(str(price))
                for tid, price in data.items()
            }
        except Exception as e:
            logger.warning(f"Batch price fetch failed: {e}")
            return {}

    # ── Order placement ─────────────────────────────────────────────────────
    async def place_limit_order(
        self, token_id: str, side: str, price: Decimal, size: Decimal
    ) -> bool:
        """
        Place a GTC limit order via py-clob-client.
        In DRY_RUN mode, only logs the intent.
        """
        from config import config
        if config.DRY_RUN:
            logger.info(
                f"[DRY RUN] {side} order: token={token_id[:8]}… "
                f"price={float(price):.4f} size={float(size):.2f}"
            )
            return True

        if not self.clob_client:
            logger.error("CLOB client not initialised — cannot place order")
            return False

        try:
            order_args = {
                "token_id": token_id,
                "side":     side.upper(),  # "BUY" or "SELL"
                "price":    float(price),
                "size":     float(size),
            }
            result = self.clob_client.create_order(order_args)
            resp   = self.clob_client.post_order(result)
            logger.info(f"Order placed: {resp}")
            return True
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return False

    # ── Gamma API extras (RobotTraders patterns) ────────────────────────────
    async def get_market_trades(self, market_id: str, limit: int = 50) -> List[dict]:
        """Fetch recent trades for a market."""
        try:
            data = await self._gamma_get(
                "/trades",
                {"market": market_id, "limit": str(limit), "order": "TIMESTAMP", "ascending": "false"}
            )
            return data if isinstance(data, list) else data.get("trades", [])
        except Exception as e:
            logger.warning(f"Trade fetch failed for {market_id}: {e}")
            return []

    async def get_volume_stats(self) -> Dict[str, Decimal]:
        """Get global Polymarket volume stats."""
        try:
            data = await self._gamma_get("/stats")
            return {
                "total_volume": Decimal(str(data.get("volume", "0"))),
                "volume_24hr":  Decimal(str(data.get("volume24hr", "0"))),
                "open_interest": Decimal(str(data.get("openInterest", "0"))),
            }
        except Exception as e:
            logger.warning(f"Stats fetch failed: {e}")
            return {}

    async def search_markets(self, query: str, limit: int = 20) -> List[dict]:
        """Search markets by keyword."""
        try:
            data = await self._gamma_get("/markets", {
                "query": query,
                "active": "true",
                "limit": str(limit),
            })
            return data if isinstance(data, list) else data.get("markets", [])
        except Exception as e:
            logger.warning(f"Market search failed: {e}")
            return []
