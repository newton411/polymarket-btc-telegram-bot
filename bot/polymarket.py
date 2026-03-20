"""
Polymarket API integration: Gamma API for market discovery and CLOB for trading
"""
import asyncio
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
    yes_asks: List[Tuple[Decimal, Decimal]]  # [(price, size), ...]
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

        # Initialize CLOB client if available
        self.clob_client = None
        if not config.DRY_RUN:
            try:
                from clob_client.client import ClobClient
                from clob_client.clob_types import ApiCredential
                from clob_client.constants import POLYGON

                creds = ApiCredential(
                    api_key=config.POLYMARKET_PRIVATE_KEY,
                    api_secret="",  # Not needed for read operations
                    api_passphrase=""
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
            # Query for BTC markets
            params = {
                'slug_contains': config.BTC_MARKET_FILTER,
                'resolution': config.RESOLUTION_FILTER,
                'active': 'true',
                'closed': 'false',
                'limit': 50
            }

            data = self._gamma_request("/markets", params)

            markets = []
            for market in data.get('markets', []):
                # Filter for BTC 5-min markets
                if ('bitcoin' in market.get('question', '').lower() and
                    '5' in market.get('resolution', '') and
                    'min' in market.get('resolution', '')):

                    # Parse outcomes and prices
                    outcomes = market.get('outcomes', [])
                    if len(outcomes) != 2:
                        continue

                    prices = []
                    for outcome in market.get('outcomePrices', []):
                        try:
                            prices.append(Decimal(str(outcome)))
                        except:
                            prices.append(Decimal('0.5'))

                    if len(prices) != 2:
                        continue

                    market_info = MarketInfo(
                        market_id=market['id'],
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2))
    async def get_orderbook(self, market_id: str) -> Optional[OrderBook]:
        """Get order book for a market."""
        try:
            if self.clob_client:
                # Use CLOB API
                book = await self.clob_client.get_order_book(market_id)
                # Parse the response
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
                # Simulate order book for dry run
                import random
                import time

                # Generate realistic simulated order book
                mid_price = Decimal('0.5') + Decimal(str(random.uniform(-0.1, 0.1)))
                spread = Decimal('0.02')

                yes_asks = [(mid_price + spread + Decimal(str(i * 0.01)), Decimal(str(random.uniform(10, 100))))
                           for i in range(5)]
                yes_bids = [(mid_price - spread - Decimal(str(i * 0.01)), Decimal(str(random.uniform(10, 100))))
                           for i in range(5)]
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
            # Create order
            order_args = {
                "market": market_id,
                "side": side.upper(),
                "price": float(price),
                "size": float(size),
                "fee_rate_bps": 0  # No fee for limit orders
            }

            # Place order
            result = await self.clob_client.create_order(order_args)
            logger.info(f"Order placed: {result}")
            return True

        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return False