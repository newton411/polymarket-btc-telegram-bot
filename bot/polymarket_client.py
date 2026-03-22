"""
Polymarket CLOB Client & Gamma API Integration
Based on RobotTraders/bits_and_bobs patterns:
  https://github.com/RobotTraders/bits_and_bobs/blob/main/polymarket_python.ipynb

Key API endpoints:
  Gamma API  (market discovery):  https://gamma-api.polymarket.com/markets
  Data API   (positions/trades):  https://data-api.polymarket.com
  CLOB API   (order book/orders): https://clob.polymarket.com

py-clob-client usage (from RobotTraders notebook):
  client = ClobClient(CLOB_API)                      # read-only
  book   = client.get_order_book(yes_token_id)       # OrderBook object
  mid    = client.get_midpoint(yes_token_id)         # {"mid": "0.62"}
  spread = client.get_spread(yes_token_id)           # {"spread": "0.02"}
  # Authenticated:
  auth_client = ClobClient(CLOB_API, key=PK, chain_id=137, ...)
  creds = auth_client.derive_api_key()
  auth_client.set_api_creds(creds)
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import aiohttp

from config import config

logger = logging.getLogger(__name__)

# ─── API base URLs ──────────────────────────────────────────────────────────
GAMMA_API  = "https://gamma-api.polymarket.com"
CLOB_API   = "https://clob.polymarket.com"
DATA_API   = "https://data-api.polymarket.com"


# ─── Data classes ───────────────────────────────────────────────────────────
@dataclass
class OrderBookSnapshot:
    """Snapshot of order book for a single outcome token."""
    token_id:  str
    mid_price: Decimal
    best_bid:  Decimal
    best_ask:  Decimal
    bid_size:  Decimal
    ask_size:  Decimal
    spread:    Decimal
    timestamp: datetime


@dataclass
class MarketInfo:
    """
    Rich market information from Gamma API.
    Mirrors the fields shown in the RobotTraders notebook:
      m['question'], m['endDate'], m['conditionId'],
      m['clobTokenIds'], m['outcomePrices'], m['volume24hr'], m['liquidityNum']
    """
    market_id:        str          # conditionId
    title:            str          # question
    end_date_iso:     str          # endDateIso / endDate
    resolution_time:  datetime
    is_active:        bool
    yes_token_id:     str = ""     # clobTokenIds[0]
    no_token_id:      str = ""     # clobTokenIds[1]
    yes_price:        Decimal = Decimal("0.5")
    no_price:         Decimal = Decimal("0.5")
    volume_24hr:      Decimal = Decimal("0")
    liquidity:        Decimal = Decimal("0")
    outcome_tokens:   List[str] = field(default_factory=list)
    order_book_yes:   Optional[OrderBookSnapshot] = None
    order_book_no:    Optional[OrderBookSnapshot] = None

    @property
    def sum_price(self) -> Decimal:
        return self.yes_price + self.no_price

    @property
    def edge(self) -> Decimal:
        """Arbitrage edge: (1 - sum) / 2."""
        return max(Decimal("0"), (Decimal("1") - self.sum_price) / Decimal("2"))

    @property
    def implied_prob_yes(self) -> Decimal:
        s = self.yes_price + self.no_price
        return self.yes_price / s if s > 0 else Decimal("0.5")


class PolymarketClient:
    """
    Async Polymarket API client implementing the full RobotTraders pattern:

      Step 1 — Market discovery via Gamma API (no auth needed)
      Step 2 — Token ID extraction (clobTokenIds JSON field)
      Step 3 — Order book fetch via CLOB API (read-only, no auth)
      Step 4 — Order placement via py-clob-client (authenticated, live only)

    All network calls are async (aiohttp). The CLOB order-book calls also
    fall back to the RobotTraders pattern of calling the REST endpoint
    directly when py-clob-client is unavailable.
    """

    def __init__(self):
        self.base_url  = config.CLOB_HOST
        self.gamma_url = config.GAMMA_API_BASE
        self.session: Optional[aiohttp.ClientSession] = None

        self.private_key = config.POLYMARKET_PRIVATE_KEY
        self.address     = config.POLYMARKET_ADDRESS

        # py-clob-client (authenticated, optional)
        self._clob_client = None
        self._clob_available = False
        self._try_import_clob()

        # In-memory cache
        self.active_markets: List[MarketInfo] = []
        self.opportunities: List = []          # filled by strategies
        self._cache_ts: float = 0.0

    def _try_import_clob(self):
        """Try to import py-clob-client (optional dependency)."""
        try:
            from py_clob_client.client import ClobClient  # noqa
            self._clob_available = True
            logger.info("✅ py-clob-client available")
        except ImportError:
            logger.warning(
                "⚠️  py-clob-client not installed — using REST fallback. "
                "Install: pip install py-clob-client"
            )

    async def initialize(self):
        """Create aiohttp session and optionally authenticate CLOB client."""
        connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
        timeout   = aiohttp.ClientTimeout(total=10)
        headers   = {
            "User-Agent": "RecondTradeBot/2.0 (Polymarket HFT)",
            "Accept":     "application/json",
        }
        self.session = aiohttp.ClientSession(
            connector=connector, timeout=timeout, headers=headers
        )

        # Authenticate CLOB client if private key present
        if self._clob_available and self.private_key:
            try:
                from py_clob_client.client import ClobClient
                self._clob_client = ClobClient(
                    CLOB_API,
                    key=self.private_key,
                    chain_id=137,          # Polygon mainnet
                    funder=self.address,
                )
                creds = self._clob_client.derive_api_key()
                self._clob_client.set_api_creds(creds)
                logger.info(f"✅ CLOB client authenticated for {self.address}")
            except Exception as e:
                logger.warning(f"⚠️  CLOB auth failed (read-only mode): {e}")
        else:
            logger.info("ℹ️  CLOB client in read-only mode (no private key)")

    async def close(self):
        if self.session:
            await self.session.close()

    # ── Gamma API — market discovery ────────────────────────────────────────
    async def discover_markets(self) -> List[MarketInfo]:
        """
        Discover active BTC 5-minute markets via Gamma API.

        Matches the RobotTraders notebook pattern:
          response = requests.get(f"{GAMMA_API}/markets", params={
              "limit": 10, "active": True, "closed": False,
              "order": "volume24hr", "ascending": False
          })
        """
        try:
            params = {
                "active":    "true",
                "closed":    "false",
                "limit":     "200",
                "order":     "volume24hr",
                "ascending": "false",
            }
            async with self.session.get(f"{GAMMA_API}/markets", params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Gamma API returned {resp.status}")
                    return self.active_markets   # return stale cache

                raw = await resp.json()
                data = raw if isinstance(raw, list) else raw.get("markets", [])

            markets: List[MarketInfo] = []
            for m in data:
                question = m.get("question", "") or m.get("title", "")
                q_lower  = question.lower()

                # ── Filter: BTC 5-minute binary market ──────────────────
                is_btc = "bitcoin" in q_lower or "btc" in q_lower
                is_5m  = ("5 min" in q_lower or "5min" in q_lower
                           or "5-min" in q_lower or "5 minute" in q_lower
                           or "five minute" in q_lower)
                if not (is_btc and is_5m):
                    continue

                # ── Parse clobTokenIds (JSON string in Gamma response) ──
                raw_token_ids = m.get("clobTokenIds", "[]")
                try:
                    token_ids: List[str] = (
                        json.loads(raw_token_ids)
                        if isinstance(raw_token_ids, str)
                        else raw_token_ids
                    )
                except Exception:
                    token_ids = []

                yes_token = token_ids[0] if len(token_ids) > 0 else ""
                no_token  = token_ids[1] if len(token_ids) > 1 else ""

                # ── Parse outcome prices ──────────────────────────────
                raw_prices = m.get("outcomePrices", "[]")
                try:
                    prices = (
                        json.loads(raw_prices)
                        if isinstance(raw_prices, str)
                        else raw_prices
                    )
                except Exception:
                    prices = []

                yes_price = Decimal(str(prices[0])) if len(prices) > 0 else Decimal("0.5")
                no_price  = Decimal(str(prices[1])) if len(prices) > 1 else Decimal("0.5")

                # ── Parse resolution time ─────────────────────────────
                end_iso = m.get("endDateIso") or m.get("endDate", "")
                try:
                    res_time = datetime.fromisoformat(
                        end_iso.replace("Z", "+00:00")
                    )
                except Exception:
                    res_time = datetime.now(timezone.utc) + timedelta(minutes=5)

                if datetime.now(timezone.utc) >= res_time:
                    continue   # already resolved

                mi = MarketInfo(
                    market_id       = m.get("conditionId") or m.get("id", ""),
                    title           = question,
                    end_date_iso    = end_iso,
                    resolution_time = res_time,
                    is_active       = bool(m.get("active", True)),
                    yes_token_id    = yes_token,
                    no_token_id     = no_token,
                    yes_price       = yes_price,
                    no_price        = no_price,
                    volume_24hr     = Decimal(str(m.get("volume24hr") or "0")),
                    liquidity       = Decimal(str(m.get("liquidityNum") or
                                                  m.get("liquidity") or "0")),
                    outcome_tokens  = token_ids,
                )
                markets.append(mi)

                if len(markets) >= 20:
                    break

            self.active_markets = markets
            self._cache_ts = time.time()
            logger.info(f"📊 Discovered {len(markets)} BTC 5-min markets (Gamma API)")
            return markets

        except Exception as e:
            logger.error(f"Market discovery failed: {e}")
            return self.active_markets   # return stale cache

    # ── CLOB API — order book (RobotTraders pattern) ───────────────────────
    async def get_order_book(self, token_id: str) -> Optional[OrderBookSnapshot]:
        """
        Fetch live order book for a token_id from CLOB.

        REST fallback (mirrors RobotTraders notebook):
          GET https://clob.polymarket.com/book?token_id=<token_id>

        py-clob-client equivalent:
          client = ClobClient(CLOB_API)
          book   = client.get_order_book(token_id)
          bids   = sorted(book.bids, key=lambda x: float(x.price), reverse=True)
          asks   = sorted(book.asks, key=lambda x: float(x.price))
        """
        if not token_id:
            return None
        try:
            url = f"{CLOB_API}/book"
            async with self.session.get(url, params={"token_id": token_id}) as resp:
                if resp.status != 200:
                    return None
                data   = await resp.json()
                bids   = sorted(data.get("bids", []), key=lambda x: float(x.get("price", 0)), reverse=True)
                asks   = sorted(data.get("asks", []), key=lambda x: float(x.get("price", 1)))

                best_bid = Decimal(str(bids[0]["price"])) if bids else Decimal("0")
                best_ask = Decimal(str(asks[0]["price"])) if asks else Decimal("1")
                bid_size = Decimal(str(bids[0].get("size", "0"))) if bids else Decimal("0")
                ask_size = Decimal(str(asks[0].get("size", "0"))) if asks else Decimal("0")
                mid      = (best_bid + best_ask) / 2
                spread   = best_ask - best_bid

                return OrderBookSnapshot(
                    token_id  = token_id,
                    mid_price = mid,
                    best_bid  = best_bid,
                    best_ask  = best_ask,
                    bid_size  = bid_size,
                    ask_size  = ask_size,
                    spread    = spread,
                    timestamp = datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.debug(f"Order book fetch failed for {token_id}: {e}")
            return None

    async def get_midpoint(self, token_id: str) -> Optional[Decimal]:
        """
        Get mid-price for a token.
        Mirrors: mid = client.get_midpoint(yes_token_id) → mid['mid']
        """
        try:
            async with self.session.get(
                f"{CLOB_API}/midpoint", params={"token_id": token_id}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return Decimal(str(data.get("mid", "0.5")))
        except Exception:
            pass
        snap = await self.get_order_book(token_id)
        return snap.mid_price if snap else None

    async def get_spread(self, token_id: str) -> Optional[Decimal]:
        """
        Get spread for a token.
        Mirrors: spread = client.get_spread(yes_token_id) → spread['spread']
        """
        try:
            async with self.session.get(
                f"{CLOB_API}/spread", params={"token_id": token_id}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return Decimal(str(data.get("spread", "0")))
        except Exception:
            pass
        snap = await self.get_order_book(token_id)
        return snap.spread if snap else None

    async def get_best_prices(
        self, token_ids: Tuple[str, str]
    ) -> Optional[Tuple[Decimal, Decimal]]:
        """Fetch best ask prices for both YES/NO tokens in parallel."""
        yes_id, no_id = token_ids
        yes_snap, no_snap = await asyncio.gather(
            self.get_order_book(yes_id),
            self.get_order_book(no_id),
            return_exceptions=True,
        )
        if isinstance(yes_snap, Exception) or not yes_snap:
            return None
        if isinstance(no_snap, Exception) or not no_snap:
            return None
        return (yes_snap.best_ask, no_snap.best_ask)

    # ── Data API — user positions ───────────────────────────────────────────
    async def get_user_positions(self, wallet_address: str) -> List[dict]:
        """
        Get a user's current positions from Data API.
        Mirrors the RobotTraders bonus function:
          def get_user_positions(wallet_address):
              url = f"{DATA_API}/positions"
              return requests.get(url, params={"user": wallet_address}).json()
        """
        try:
            async with self.session.get(
                f"{DATA_API}/positions", params={"user": wallet_address}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Failed to get positions for {wallet_address}: {e}")
        return []

    # ── CLOB — live market price tracking ──────────────────────────────────
    async def track_token_prices(
        self, token_ids: List[str], duration: int = 30
    ) -> Dict[str, List[float]]:
        """
        Track price changes for multiple tokens over `duration` seconds.
        Implements the RobotTraders Price Tracker pattern:
          while time.time() - start_time < duration:
              mid = client.get_midpoint(token_id)
        """
        history: Dict[str, List[float]] = {tid: [] for tid in token_ids}
        start = time.time()

        while time.time() - start < duration:
            tasks = [self.get_midpoint(tid) for tid in token_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for tid, price in zip(token_ids, results):
                if not isinstance(price, Exception) and price:
                    history[tid].append(float(price))
            await asyncio.sleep(1)

        return history

    # ── CLOB — order placement ─────────────────────────────────────────────
    async def create_order(
        self,
        token_id:   str,
        side:       str,        # "BUY" or "SELL"
        size:       Decimal,
        price:      Decimal,
        order_type: str = "GTC",
    ) -> Optional[str]:
        """
        Create and post a GTC or FOK order.

        py-clob-client pattern (from RobotTraders):
          limit_order  = OrderArgs(token_id=..., price=0.60, size=10.0, side=BUY)
          signed_order = auth_client.create_order(limit_order)
          response     = auth_client.post_order(signed_order, OrderType.GTC)

        In DRY_RUN mode, logs the intent without placing a real order.
        """
        if config.DRY_RUN:
            logger.info(
                f"[DRY_RUN] {side} {float(size):.2f} shares "
                f"@ ${float(price):.4f} on {token_id[:12]}…"
            )
            return f"dry_{int(time.time())}"

        if not self._clob_client:
            logger.error("❌ CLOB client not initialized — cannot place live order")
            return None

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL

            order_args = OrderArgs(
                token_id = token_id,
                price    = float(price),
                size     = float(size),
                side     = BUY if side.upper() == "BUY" else SELL,
            )
            ot = OrderType.GTC if order_type == "GTC" else OrderType.FOK
            signed = self._clob_client.create_order(order_args)
            resp   = self._clob_client.post_order(signed, ot)
            order_id = resp.get("orderID") or resp.get("order_id", "")
            logger.info(f"✅ Order placed: {order_id}")
            return order_id

        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}")
            return None

    async def create_market_order(
        self, token_id: str, amount_usd: float, side: str = "BUY"
    ) -> Optional[str]:
        """
        Place a market FOK order (spend `amount_usd` dollars).
        Mirrors the RobotTraders notebook FOK pattern:
          market_order = MarketOrderArgs(token_id=..., amount=5.0, side=BUY, order_type=FOK)
        """
        if config.DRY_RUN:
            logger.info(f"[DRY_RUN] Market {side} ${amount_usd:.2f} on {token_id[:12]}…")
            return f"dry_{int(time.time())}"

        if not self._clob_client:
            return None

        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL

            args   = MarketOrderArgs(
                token_id   = token_id,
                amount     = amount_usd,
                side       = BUY if side.upper() == "BUY" else SELL,
                order_type = OrderType.FOK,
            )
            signed = self._clob_client.create_market_order(args)
            resp   = self._clob_client.post_order(signed, OrderType.FOK)
            return resp.get("orderID", "")
        except Exception as e:
            logger.error(f"❌ Market order failed: {e}")
            return None

    # ── Account management ─────────────────────────────────────────────────
    async def check_user_balance(self) -> Optional[Decimal]:
        """
        Get USDC balance.
        Mirrors: balance = auth_client.get_balance_allowance(...)
                 usdc_balance = int(balance['balance']) / 1e6
        """
        if not self._clob_client:
            return None
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            bal = self._clob_client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            return Decimal(str(int(bal["balance"]) / 1_000_000))
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return None

    async def get_open_orders(self) -> List[Dict]:
        """
        Fetch open orders.
        Mirrors: open_orders = auth_client.get_orders(OpenOrderParams())
        """
        if not self._clob_client:
            return []
        try:
            from py_clob_client.clob_types import OpenOrderParams
            return self._clob_client.get_orders(OpenOrderParams()) or []
        except Exception as e:
            logger.error(f"get_open_orders failed: {e}")
            return []

    async def cancel_order(self, order_id: str) -> bool:
        if config.DRY_RUN:
            logger.info(f"[DRY_RUN] Would cancel {order_id}")
            return True
        if not self._clob_client:
            return False
        try:
            self._clob_client.cancel(order_id)
            return True
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        if config.DRY_RUN:
            logger.info("[DRY_RUN] Would cancel all orders")
            return True
        if not self._clob_client:
            return False
        try:
            self._clob_client.cancel_all()
            return True
        except Exception as e:
            logger.error(f"Cancel-all failed: {e}")
            return False

    # ── Continuous polling ─────────────────────────────────────────────────
    async def poll_markets_continuously(
        self, markets: List[MarketInfo], callback=None
    ):
        """Continuously poll YES/NO order books for given markets."""
        while True:
            try:
                for m in markets:
                    if not m.is_active or not m.yes_token_id:
                        continue
                    yes_snap, no_snap = await asyncio.gather(
                        self.get_order_book(m.yes_token_id),
                        self.get_order_book(m.no_token_id),
                        return_exceptions=True,
                    )
                    m.order_book_yes = yes_snap if not isinstance(yes_snap, Exception) else None
                    m.order_book_no  = no_snap  if not isinstance(no_snap,  Exception) else None

                    if m.order_book_yes:
                        m.yes_price = m.order_book_yes.best_ask
                    if m.order_book_no:
                        m.no_price  = m.order_book_no.best_ask

                    if callback and m.order_book_yes and m.order_book_no:
                        await callback(m.market_id, m.yes_price, m.no_price)

                await asyncio.sleep(config.POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
                await asyncio.sleep(5)
