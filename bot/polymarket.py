"""
Polymarket API integration: Gamma API for market discovery and CLOB trading.
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config

logger = logging.getLogger(__name__)

@dataclass
class MarketInfo:
    """Market information from Gamma API."""
    market_id: str
    question: str
    active: bool
    closed: bool
    end_date_iso: str
    volume: Decimal
    volume_24hr: Decimal
    outcomes: List[str]
    prices: List[Decimal]

@dataclass
class OrderBook:
    """Order book snapshot."""
    market_id: str
    yes_asks: List[Tuple[Decimal, Decimal]]
    yes_bids: List[Tuple[Decimal, Decimal]]
    no_asks: List[Tuple[Decimal, Decimal]]
    no_bids: List[Tuple[Decimal, Decimal]]
    timestamp: float

class PolymarketClient:
    """Polymarket API client for market discovery and CLOB operations."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PolymarketBTCBot/1.0',
            'Accept': 'application/json'
        })

        self.clob_client = None
        if not config.DRY_RUN:
            try:
                from clob_client.client import ClobClient
                from clob_client.clob_types import ApiCredential
                from clob_client.constants import POLYGON

                creds = ApiCredential(
                    api_key=config.POLYMARKET_API_KEY,
                    api_secret=config.POLYMARKET_API_SECRET or "",
                    api_passphrase=config.POLYMARKET_API_PASSPHRASE or ""
                )

                self.clob_client = ClobClient(
                    host=config.CLOB_HOST,
                    key=creds,
                    chain_id=POLYGON
                )
                logger.info("CLOB client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize CLOB client: {e}")
                self.clob_client = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _gamma_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make request to Gamma API with retry logic."""
        url = f"{config.GAMMA_API_BASE}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Gamma API request failed: {e}")
            raise

    async def discover_btc_markets(self) -> List[MarketInfo]:
        """Discover active 5-minute BTC Up/Down markets."""
        try:
            params = {
                'slug_contains': config.BTC_MARKET_FILTER,
                'resolution': config.RESOLUTION_FILTER,
                'active': 'true',
                'closed': 'false',
                'limit': 50
            }

            data = self._gamma_request("/markets", params)

            markets_response = []
            if isinstance(data, dict) and 'markets' in data:
                markets_response = data['markets']
            elif isinstance(data, list):
                markets_response = data

            markets = []

            def _is_btc_5m(market):
                q = market.get('question', '').lower()
                s = market.get('slug', '').lower()
                res = market.get('resolution', '') or ''
                res_name = (market.get('resolutionName', '') or '').lower()

                is_btc = 'bitcoin' in q or 'bitcoin' in s or 'btc' in q or 'btc' in s
                has_5m = '5' in res or '5' in res_name or 'min' in res or 'minute' in res_name
                return is_btc and has_5m

            filter_candidates = [m for m in markets_response if _is_btc_5m(m)]
            if not filter_candidates:
                filter_candidates = markets_response[:10]

            for market in filter_candidates:
                if not market.get('question'):
                    market['question'] = market.get('slug', 'Unknown market')

                outcomes = market.get('outcomes', [])
                if isinstance(outcomes, str):
                    try:
                        outcomes = json.loads(outcomes)
                    except Exception:
                        outcomes = []
                if len(outcomes) != 2:
                    continue

                outcome_prices = market.get('outcomePrices', [])
                if isinstance(outcome_prices, str):
                    try:
                        outcome_prices = json.loads(outcome_prices)
                    except Exception:
                        outcome_prices = []

                prices = []
                for outcome in outcome_prices:
                    try:
                        prices.append(Decimal(str(outcome)))
                    except Exception:
                        prices.append(Decimal('0.5'))

                if len(prices) != 2:
                    continue

                market_info = MarketInfo(
                    market_id=market.get('id', ''),
                    question=market.get('question', ''),
                    active=market.get('active', False),
                    closed=market.get('closed', False),
                    end_date_iso=market.get('endDateIso', ''),
                    volume=Decimal(str(market.get('volume', '0'))),
                    volume_24hr=Decimal(str(market.get('volume24hr', '0'))),
                    outcomes=outcomes,
                    prices=prices
                )
                markets.append(market_info)

            logger.info(f"Discovered {len(markets)} BTC 5-min markets")
            return markets

        except Exception as e:
            logger.error(f"Market discovery failed: {e}")
            return []

    def get_market_details(self, market_id: str) -> Optional[Dict]:
        """Fetch individual market details from Gamma API."""
        try:
            data = self._gamma_request(f"/markets/{market_id}")
            return data
        except Exception as e:
            logger.warning(f"Unable to fetch market data for {market_id}: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2))
    async def get_orderbook(self, market_id: str) -> Optional[OrderBook]:
        """Get order book for a market."""
        try:
            if self.clob_client:
                book = await self.clob_client.get_order_book(market_id)
                yes_asks = [(Decimal(str(p)), Decimal(str(s))) for p, s in book.get('asks', {}).get('yes', [])]
                yes_bids = [(Decimal(str(p)), Decimal(str(s))) for p, s in book.get('bids', {}).get('yes', [])]
                no_asks = [(Decimal(str(p)), Decimal(str(s))) for p, s in book.get('asks', {}).get('no', [])]
                no_bids = [(Decimal(str(p)), Decimal(str(s))) for p, s in book.get('bids', {}).get('no', [])]

                return OrderBook(
                    market_id=market_id,
                    yes_asks=yes_asks,
                    yes_bids=yes_bids,
                    no_asks=no_asks,
                    no_bids=no_bids,
                    timestamp=asyncio.get_event_loop().time()
                )
            else:
                import random
                import time

                mid_price = Decimal('0.5') + Decimal(str(random.uniform(-0.1, 0.1)))
                spread = Decimal('0.02')

                yes_asks = [(mid_price + spread + Decimal(str(i * 0.01)), Decimal(str(random.uniform(10, 100)))) for i in range(5)]
                yes_bids = [(mid_price - spread - Decimal(str(i * 0.01)), Decimal(str(random.uniform(10, 100)))) for i in range(5)]
                no_asks = [(Decimal('1') - p, s) for p, s in yes_bids]
                no_bids = [(Decimal('1') - p, s) for p, s in yes_asks]

                return OrderBook(
                    market_id=market_id,
                    yes_asks=yes_asks,
                    yes_bids=yes_bids,
                    no_asks=no_asks,
                    no_bids=no_bids,
                    timestamp=time.time()
                )

        except Exception as e:
            logger.error(f"Order book fetch failed for {market_id}: {e}")
            return None

    def get_best_prices(self, orderbook: OrderBook) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Extract best bid/ask prices from order book."""
        try:
            best_yes_bid = max(orderbook.yes_bids, key=lambda x: x[0])[0] if orderbook.yes_bids else None
            best_yes_ask = min(orderbook.yes_asks, key=lambda x: x[0])[0] if orderbook.yes_asks else None
            best_no_bid = max(orderbook.no_bids, key=lambda x: x[0])[0] if orderbook.no_bids else None
            best_no_ask = min(orderbook.no_asks, key=lambda x: x[0])[0] if orderbook.no_asks else None

            return best_yes_bid, best_yes_ask, best_no_bid, best_no_ask
        except Exception as e:
            logger.error(f"Price extraction failed: {e}")
            return None, None, None, None

    async def place_limit_order(self, market_id: str, side: str, price: Decimal, size: Decimal) -> bool:
        """Place a limit order (or simulate in dry run)."""
        if config.DRY_RUN:
            logger.info(f"DRY RUN: Would place {side} order for {market_id} at {price} size {size}")
            return True

        if not self.clob_client:
            logger.error("CLOB client not available for live trading")
            return False

        try:
            order_args = {
                "market": market_id,
                "side": side.upper(),
                "price": float(price),
                "size": float(size),
                "fee_rate_bps": 0
            }

            result = await self.clob_client.create_order(order_args)
            logger.info(f"Order placed: {result}")
            return True

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return False
