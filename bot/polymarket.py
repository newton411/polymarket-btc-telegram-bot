"""
Polymarket API client — Gamma API (market data) + CLOB API (order books & trading)

Patterns directly from RobotTraders/bits_and_bobs/polymarket_python.ipynb:
  https://github.com/RobotTraders/bits_and_bobs/blob/main/polymarket_python.ipynb

Key APIs:
  Gamma API : https://gamma-api.polymarket.com/markets   (free, no auth)
  CLOB API  : https://clob.polymarket.com                 (auth for orders, public for book)
  Data API  : https://data-api.polymarket.com             (user positions, history)
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import aiohttp
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"
DATA_API  = "https://data-api.polymarket.com"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class TokenInfo:
    """YES or NO token for a binary market."""
    token_id: str
    outcome: str      # "Yes" or "No"
    price: Decimal = Decimal("0.5")
    winner: bool = False


@dataclass
class MarketInfo:
    """
    Rich market information from Gamma API.
    Mirrors the market dict from RobotTraders notebook.
    """
    market_id: str        # conditionId or slug
    question: str
    active: bool
    closed: bool
    end_date_iso: str
    volume: Decimal
    volume_24hr: Decimal
    liquidity: Decimal
    outcomes: List[str]
    prices: List[Decimal]          # [yes_price, no_price]
    tokens: List[TokenInfo] = field(default_factory=list)
    condition_id: str = ""
    clob_token_ids: List[str] = field(default_factory=list)

    @property
    def yes_price(self) -> Decimal:
        return self.prices[0] if self.prices else Decimal("0.5")

    @property
    def no_price(self) -> Decimal:
        return self.prices[1] if len(self.prices) > 1 else Decimal("0.5")

    @property
    def spread(self) -> Decimal:
        return abs(self.yes_price + self.no_price - Decimal("1"))

    @property
    def edge(self) -> Decimal:
        """Implied edge = 1 - (YES + NO) i.e. how much less than $1 you pay."""
        return Decimal("1") - (self.yes_price + self.no_price)

    @property
    def yes_token_id(self) -> Optional[str]:
        return self.clob_token_ids[0] if self.clob_token_ids else (
            next((t.token_id for t in self.tokens if "yes" in t.outcome.lower()), None)
        )

    @property
    def no_token_id(self) -> Optional[str]:
        return self.clob_token_ids[1] if len(self.clob_token_ids) > 1 else (
            next((t.token_id for t in self.tokens if "no" in t.outcome.lower()), None)
        )


@dataclass
class OrderLevel:
    price: Decimal
    size: Decimal


@dataclass
class OrderBook:
    """
    CLOB order book snapshot.
    Bids = buy orders (highest first), Asks = sell orders (lowest first).
    """
    token_id: str
    bids: List[OrderLevel] = field(default_factory=list)
    asks: List[OrderLevel] = field(default_factory=list)
    timestamp: float = 0.0
    mid: Decimal = Decimal("0.5")
    spread: Decimal = Decimal("0")

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None

    @property
    def depth_bid(self) -> Decimal:
        return sum(lvl.size for lvl in self.bids[:5])

    @property
    def depth_ask(self) -> Decimal:
        return sum(lvl.size for lvl in self.asks[:5])


# ── Client ────────────────────────────────────────────────────────────────────

class PolymarketClient:
    """
    Async Polymarket API client combining Gamma + CLOB.

    Usage pattern from RobotTraders notebook:
        client = ClobClient(CLOB_API)             # read-only
        book = client.get_order_book(token_id)    # fetch order book
        mid  = client.get_midpoint(token_id)      # get midpoint

    This async version wraps all calls in aiohttp for non-blocking I/O.
    The sync `requests` session is used as a fallback where needed.
    """

    def __init__(self):
        self._async_session: Optional[aiohttp.ClientSession] = None
        self._sync_session = requests.Session()
        self._sync_session.headers.update({
            "User-Agent": "RecondTrade/2.0 (Polymarket BTC Bot)",
            "Accept": "application/json",
        })

        # Authenticated CLOB client (optional — for order placement)
        self.clob_client = None
        self._market_cache: Dict[str, MarketInfo] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 30.0   # seconds

    # ── Session helpers ───────────────────────────────────────────────────────

    async def _session(self) -> aiohttp.ClientSession:
        if self._async_session is None or self._async_session.closed:
            timeout = aiohttp.ClientTimeout(total=12)
            self._async_session = aiohttp.ClientSession(
                headers={"User-Agent": "RecondTrade/2.0", "Accept": "application/json"},
                timeout=timeout,
            )
        return self._async_session

    async def initialize(self):
        """Initialize authenticated CLOB client if credentials are set."""
        if config.DRY_RUN:
            logger.info("DRY_RUN mode — CLOB client skipped")
            return
        try:
            from py_clob_client.client import ClobClient as _ClobClient
            pk = config.POLYMARKET_PRIVATE_KEY
            addr = config.POLYMARKET_ADDRESS
            if pk:
                self.clob_client = _ClobClient(
                    CLOB_API,
                    key=pk,
                    chain_id=137,   # Polygon mainnet (from RobotTraders: chain_id=137)
                    signature_type=1,  # Email/Magic wallet
                    funder=addr,
                )
                creds = self.clob_client.derive_api_key()
                self.clob_client.set_api_creds(creds)
                logger.info("Polymarket CLOB client authenticated")
        except ImportError:
            logger.warning("py-clob-client not installed — using simulation mode")
        except Exception as e:
            logger.error(f"CLOB auth failed: {e}")

    async def close(self):
        if self._async_session and not self._async_session.closed:
            await self._async_session.close()
        self._sync_session.close()

    # ── Gamma API — Market Discovery ──────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _gamma_get(self, path: str, params: Optional[Dict] = None) -> object:
        s = await self._session()
        async with s.get(f"{GAMMA_API}{path}", params=params) as r:
            r.raise_for_status()
            return await r.json()

    async def discover_btc_markets(self) -> List[MarketInfo]:
        """
        Discover active BTC 5-minute binary markets from Gamma API.

        RobotTraders pattern:
            response = requests.get(f"{GAMMA_API}/markets",
                params={"limit": 10, "active": True, "closed": False,
                        "order": "volume24hr", "ascending": False})
            markets = response.json()
        """
        now = time.time()
        if self._market_cache and (now - self._cache_ts) < self._cache_ttl:
            return list(self._market_cache.values())

        try:
            # Exact params pattern from RobotTraders notebook
            data = await self._gamma_get("/markets", {
                "active":    "true",
                "closed":    "false",
                "limit":     "100",
                "order":     "volume24hr",
                "ascending": "false",
            })
            raw = data if isinstance(data, list) else data.get("markets", [])
        except Exception as e:
            logger.error(f"Gamma market discovery failed: {e}")
            return list(self._market_cache.values())

        markets: List[MarketInfo] = []
        for m in raw:
            q = (m.get("question") or m.get("title") or "").lower()
            # Filter BTC 5-minute markets
            if not (("bitcoin" in q or "btc" in q) and
                    any(t in q for t in ("5 min", "5min", "5-min", "five min"))):
                continue

            # Parse clobTokenIds — stored as JSON string in Gamma response
            clob_ids: List[str] = []
            raw_ids = m.get("clobTokenIds") or "[]"
            try:
                clob_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
            except Exception:
                pass

            # Parse outcomes
            outcomes = m.get("outcomes", [])
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except Exception:
                    outcomes = []

            # Parse outcomePrices
            raw_prices = m.get("outcomePrices", [])
            if isinstance(raw_prices, str):
                try:
                    raw_prices = json.loads(raw_prices)
                except Exception:
                    raw_prices = []

            prices = []
            for p in raw_prices:
                try:
                    prices.append(Decimal(str(p)))
                except Exception:
                    prices.append(Decimal("0.5"))

            if len(prices) < 2:
                prices = [Decimal("0.5"), Decimal("0.5")]

            # Build token objects
            tokens = []
            for t in (m.get("tokens") or []):
                tokens.append(TokenInfo(
                    token_id=t.get("token_id", ""),
                    outcome=t.get("outcome", ""),
                    price=Decimal(str(t.get("price", "0.5"))),
                    winner=bool(t.get("winner", False)),
                ))

            mi = MarketInfo(
                market_id=m.get("conditionId") or m.get("id", ""),
                question=m.get("question") or m.get("title") or "",
                active=bool(m.get("active", False)),
                closed=bool(m.get("closed", False)),
                end_date_iso=m.get("endDateIso") or m.get("endDate") or "",
                volume=Decimal(str(m.get("volume") or "0")),
                volume_24hr=Decimal(str(m.get("volume24hr") or "0")),
                liquidity=Decimal(str(m.get("liquidityNum") or m.get("liquidity") or "0")),
                outcomes=outcomes,
                prices=prices,
                tokens=tokens,
                condition_id=m.get("conditionId", ""),
                clob_token_ids=clob_ids,
            )
            markets.append(mi)

        logger.info(f"[Gamma API] Discovered {len(markets)} active BTC 5-min markets")
        self._market_cache = {m.market_id: m for m in markets}
        self._cache_ts = now
        return markets

    async def get_market_details(self, market_id: str) -> Optional[Dict]:
        """
        Fetch single market — RobotTraders:
            print(f"Market: {market['question']}")
            print(f"End Date: {market['endDate']}")
            print(f"Condition ID: {market['conditionId']}")
        """
        try:
            data = await self._gamma_get(f"/markets", {"id": market_id})
            items = data if isinstance(data, list) else data.get("markets", [])
            return items[0] if items else None
        except Exception as e:
            logger.warning(f"Market detail fetch failed: {e}")
            return None

    async def search_markets(self, query: str, limit: int = 20) -> List[Dict]:
        """Search markets by keyword."""
        try:
            data = await self._gamma_get("/markets", {
                "active": "true", "limit": str(limit), "query": query,
                "order": "volume24hr", "ascending": "false",
            })
            return data if isinstance(data, list) else data.get("markets", [])
        except Exception as e:
            logger.warning(f"Market search failed: {e}")
            return []

    # ── CLOB API — Order Books ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _clob_get(self, path: str, params: Optional[Dict] = None) -> object:
        s = await self._session()
        async with s.get(f"{CLOB_API}{path}", params=params) as r:
            r.raise_for_status()
            return await r.json()

    async def get_orderbook(self, token_id: str) -> OrderBook:
        """
        Fetch CLOB order book for a token.

        RobotTraders pattern:
            book = client.get_order_book(yes_token_id)
            sorted_bids = sorted(book.bids, key=lambda x: float(x.price), reverse=True)
            sorted_asks = sorted(book.asks, key=lambda x: float(x.price), reverse=False)
            for ask in sorted_asks[:5]:
                print(f"Price: {ask.price} | Size: {ask.size}")
        """
        try:
            data = await self._clob_get("/book", {"token_id": token_id})
            raw_bids = data.get("bids", [])
            raw_asks = data.get("asks", [])

            bids = sorted(
                [OrderLevel(Decimal(str(b["price"])), Decimal(str(b["size"]))) for b in raw_bids],
                key=lambda x: x.price, reverse=True
            )
            asks = sorted(
                [OrderLevel(Decimal(str(a["price"])), Decimal(str(a["size"]))) for a in raw_asks],
                key=lambda x: x.price
            )

            mid = Decimal("0.5")
            spread = Decimal("0")
            if bids and asks:
                mid = (bids[0].price + asks[0].price) / 2
                spread = asks[0].price - bids[0].price

            return OrderBook(
                token_id=token_id,
                bids=bids,
                asks=asks,
                timestamp=time.time(),
                mid=mid,
                spread=spread,
            )
        except Exception as e:
            logger.warning(f"CLOB book fetch failed for {token_id}: {e}")
            return self._simulated_book(token_id)

    async def get_midpoint(self, token_id: str) -> Decimal:
        """
        Get midpoint price for a token.
        RobotTraders: mid = client.get_midpoint(yes_token_id)
        """
        try:
            data = await self._clob_get("/midpoint", {"token_id": token_id})
            return Decimal(str(data.get("mid", "0.5")))
        except Exception:
            return Decimal("0.5")

    async def get_spread(self, token_id: str) -> Decimal:
        """
        RobotTraders: spread = client.get_spread(yes_token_id)
        """
        try:
            data = await self._clob_get("/spread", {"token_id": token_id})
            return Decimal(str(data.get("spread", "0")))
        except Exception:
            return Decimal("0")

    async def get_price(self, token_id: str, side: str = "BUY") -> Decimal:
        """
        RobotTraders: buy_price = client.get_price(yes_token_id, side="BUY")
        """
        try:
            data = await self._clob_get("/price", {"token_id": token_id, "side": side})
            return Decimal(str(data.get("price", "0.5")))
        except Exception:
            return Decimal("0.5")

    async def track_token_price(self, token_id: str) -> Dict:
        """
        Real-time price tracker (RobotTraders BONUS 1 pattern).
        Returns current price with change.
        """
        mid = await self.get_midpoint(token_id)
        spread = await self.get_spread(token_id)
        buy_price = await self.get_price(token_id, "BUY")
        sell_price = await self.get_price(token_id, "SELL")
        return {
            "token_id": token_id,
            "mid": mid,
            "spread": spread,
            "best_ask": buy_price,
            "best_bid": sell_price,
            "timestamp": time.time(),
        }

    # ── Data API — User Positions ─────────────────────────────────────────────

    async def get_user_positions(self, wallet_address: str) -> List[Dict]:
        """
        RobotTraders BONUS 2 pattern:
            def get_user_positions(wallet_address):
                url = f"{DATA_API}/positions"
                params = {"user": wallet_address}
                response = requests.get(url, params=params)
                return response.json()
        """
        try:
            s = await self._session()
            async with s.get(f"{DATA_API}/positions", params={"user": wallet_address}) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            logger.warning(f"User positions fetch failed: {e}")
            return []

    async def get_usdc_balance(self) -> Decimal:
        """
        RobotTraders:
            balance = auth_client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
            usdc_balance = int(balance['balance']) / 1e6
        """
        if not self.clob_client:
            return Decimal("0")
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            balance = self.clob_client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            return Decimal(str(int(balance["balance"]) / 1e6))
        except Exception as e:
            logger.warning(f"Balance fetch failed: {e}")
            return Decimal("0")

    # ── Order placement ────────────────────────────────────────────────────────

    async def place_market_order(self, token_id: str, amount_usd: float, side: str = "BUY") -> bool:
        """
        Place a market order (FOK = Fill-or-Kill).
        RobotTraders:
            market_order = MarketOrderArgs(token_id=yes_token_id, amount=5.0, side=BUY, order_type=OrderType.FOK)
            signed = auth_client.create_market_order(market_order)
            response = auth_client.post_order(signed, OrderType.FOK)
        """
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Market {side} order: token={token_id[:12]}… amount=${amount_usd:.2f}")
            return True
        if not self.clob_client:
            logger.error("CLOB client not initialized for live trading")
            return False
        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            s = BUY if side.upper() == "BUY" else SELL
            order = MarketOrderArgs(token_id=token_id, amount=amount_usd, side=s, order_type=OrderType.FOK)
            signed = self.clob_client.create_market_order(order)
            resp = self.clob_client.post_order(signed, OrderType.FOK)
            logger.info(f"Market order placed: {resp}")
            return True
        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return False

    async def place_limit_order(self, token_id: str, price: Decimal, size: Decimal, side: str = "BUY") -> bool:
        """
        Place a GTC limit order.
        RobotTraders:
            limit_order = OrderArgs(token_id=yes_token_id, price=0.50, size=10.0, side=BUY)
            signed_order = auth_client.create_order(limit_order)
            response = auth_client.post_order(signed_order, OrderType.GTC)
        """
        if config.DRY_RUN:
            logger.info(f"[DRY RUN] Limit {side}: token={token_id[:12]}… price={float(price):.4f} size={float(size):.2f}")
            return True
        if not self.clob_client:
            logger.error("CLOB client not initialized")
            return False
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            s = BUY if side.upper() == "BUY" else SELL
            order = OrderArgs(token_id=token_id, price=float(price), size=float(size), side=s)
            signed = self.clob_client.create_order(order)
            resp = self.clob_client.post_order(signed, OrderType.GTC)
            logger.info(f"Limit order placed: {resp}")
            return True
        except Exception as e:
            logger.error(f"Limit order failed: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """RobotTraders: auth_client.cancel_all()"""
        if not self.clob_client:
            return False
        try:
            result = self.clob_client.cancel_all()
            logger.info(f"All orders cancelled: {result}")
            return True
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
            return False

    # ── Best prices helper ────────────────────────────────────────────────────

    def get_best_prices(self, book: OrderBook) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Return (best_bid, best_ask) from an order book."""
        return book.best_bid, book.best_ask

    # ── Simulation ────────────────────────────────────────────────────────────

    def _simulated_book(self, token_id: str) -> OrderBook:
        """Realistic dry-run order book when CLOB is unavailable."""
        import random
        mid = Decimal("0.5") + Decimal(str(round(random.uniform(-0.15, 0.15), 3)))
        spread = Decimal("0.012")
        bids = [OrderLevel(mid - spread - Decimal(str(i * 0.008)), Decimal(str(round(random.uniform(50, 300), 2)))) for i in range(5)]
        asks = [OrderLevel(mid + spread + Decimal(str(i * 0.008)), Decimal(str(round(random.uniform(50, 300), 2)))) for i in range(5)]
        return OrderBook(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=time.time(),
            mid=mid,
            spread=spread * 2,
        )
