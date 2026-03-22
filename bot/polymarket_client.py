"""
Polymarket CLOB Client & Gamma API Integration
Handles order book polling, market discovery, and order placement
Uses official py-clob-client library for authentication and order management
"""
import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import aiohttp
import json
from datetime import datetime, timezone, timedelta

from config import config

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSnapshot:
    """Snapshot of order book for a single outcome token"""
    mid_price: Decimal
    best_bid: Decimal
    best_ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    timestamp: datetime


@dataclass
class MarketInfo:
    """Information about a Polymarket"""
    market_id: str
    title: str
    outcome_tokens: List[str]  # e.g., ["BTC Goes Up", "BTC Goes Down"]
    resolution_time: datetime
    is_active: bool
    order_book_up: Optional[OrderBookSnapshot] = None
    order_book_down: Optional[OrderBookSnapshot] = None


class PolymarketClient:
    """
    Main client for interacting with Polymarket CLOB and Gamma API.
    
    Key Methods:
    - discover_markets(): Find active 5-min BTC Up/Down markets via Gamma API
    - get_order_book(): Poll order books for both legs
    - create_and_post_order(): Place limit orders (GTC or FOK)
    - get_midpoint(): Get price for a token
    """

    def __init__(self):
        """Initialize Polymarket client with config credentials."""
        self.base_url = config.CLOB_HOST
        self.gamma_url = config.GAMMA_API_BASE
        self.session: Optional[aiohttp.ClientSession] = None
        self.private_key = config.POLYMARKET_PRIVATE_KEY
        self.address = config.POLYMARKET_ADDRESS
        
        # Import py-clob-client components
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import Order
            self.ClobClient = ClobClient
            self.Order = Order
            self.clob_client = None
        except ImportError as e:
            logger.error(f"❌ py-clob-client not installed: {e}")
            logger.error("Install with: pip install py-clob-client")
            raise

    async def initialize(self):
        """Initialize HTTP session and CLOB client."""
        self.session = aiohttp.ClientSession()
        
        # Initialize CLOB client (requires py-clob-client)
        try:
            self.clob_client = self.ClobClient(
                host=self.base_url,
                key=self.private_key,
                address=self.address
            )
            logger.info(f"✅ CLOB Client initialized for {self.address}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize CLOB client: {e}")
            raise

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    async def discover_markets(self) -> List[MarketInfo]:
        """
        Discover active 5-minute BTC Up/Down markets via Gamma API.
        
        Returns:
            List of MarketInfo for markets matching:
            - Title contains "bitcoin" or "BTC"
            - Resolution is "5m" or similar
            - Market is active
        """
        try:
            url = f"{self.gamma_url}/markets"
            params = {
                "active": "true",
                "archived": "false",
            }
            
            async with self.session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"❌ Gamma API error: {resp.status}")
                    return []
                
                data = await resp.json()
                markets = data.get("markets", [])
                
                # Filter for BTC 5-min markets with Up/Down outcomes
                btc_markets = []
                for market in markets:
                    title = market.get("title", "").lower()
                    
                    # Check if BTC market
                    if "bitcoin" not in title and "btc" not in title:
                        continue
                    
                    # Check if 5-minute resolution
                    if "5m" not in title and "5min" not in title:
                        continue
                    
                    # Check outcomes
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) != 2:
                        continue
                    
                    # Check for Up/Down outcomes
                    outcome_texts = [o.get("name", "").lower() for o in outcomes]
                    has_up = any("up" in t or "yes" in t for t in outcome_texts)
                    has_down = any("down" in t or "no" in t for t in outcome_texts)
                    
                    if not (has_up and has_down):
                        continue
                    
                    # Parse resolution time
                    end_date_iso = market.get("endDateIso", "")
                    try:
                        resolution_time = datetime.fromisoformat(
                            end_date_iso.replace("Z", "+00:00")
                        )
                    except:
                        resolution_time = datetime.now(timezone.utc) + timedelta(hours=1)
                    
                    # Check if market is still active (not resolved yet)
                    if datetime.now(timezone.utc) >= resolution_time:
                        continue
                    
                    # Add to results
                    market_info = MarketInfo(
                        market_id=market.get("id", ""),
                        title=market.get("title", ""),
                        outcome_tokens=[o.get("id", "") for o in outcomes],
                        resolution_time=resolution_time,
                        is_active=True,
                    )
                    btc_markets.append(market_info)
                    
                    if len(btc_markets) >= 10:  # Limit to 10 active markets
                        break
                
                logger.info(f"📊 Found {len(btc_markets)} active BTC 5-min markets")
                return btc_markets
                
        except Exception as e:
            logger.error(f"❌ Failed to discover markets: {e}")
            return []

    async def get_order_book(self, token_id: str) -> Optional[OrderBookSnapshot]:
        """
        Get current order book snapshot for a token.
        
        Args:
            token_id: The outcome token ID
            
        Returns:
            OrderBookSnapshot with mid, bid, ask prices
        """
        try:
            url = f"{self.base_url}/order-book/{token_id}"
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                bids = data.get("bids", [])
                asks = data.get("asks", [])
                
                # Extract best bid/ask
                best_bid = Decimal(bids[0][0]) if bids else Decimal("0")
                best_ask = Decimal(asks[0][0]) if asks else Decimal("1")
                mid = (best_bid + best_ask) / 2
                
                bid_size = Decimal(bids[0][1]) if bids else Decimal("0")
                ask_size = Decimal(asks[0][1]) if asks else Decimal("0")
                
                return OrderBookSnapshot(
                    mid_price=mid,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    bid_size=bid_size,
                    ask_size=ask_size,
                    timestamp=datetime.now(timezone.utc)
                )
        except Exception as e:
            logger.debug(f"Failed to get order book for {token_id}: {e}")
            return None

    async def get_midpoint(self, token_id: str) -> Optional[Decimal]:
        """Get mid-price for a token."""
        snapshot = await self.get_order_book(token_id)
        if snapshot:
            return snapshot.mid_price
        return None

    async def create_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        size: Decimal,
        price: Decimal,
        order_type: str = "GTC",  # "GTC" (Good-Till-Cancel) or "FOK" (Fill-Or-Kill)
    ) -> Optional[str]:
        """
        Create and post an order to CLOB.
        
        Args:
            token_id: Outcome token ID
            side: "BUY" or "SELL"
            size: Number of shares
            price: Price per share
            order_type: "GTC" or "FOK"
            
        Returns:
            Order ID if successful, None otherwise
        """
        if not self.clob_client:
            logger.error("❌ CLOB client not initialized")
            return None
        
        if config.DRY_RUN:
            logger.info(f"🌙 DRY_RUN: Would place {side} {size} @ ${price} on {token_id}")
            return f"dry_run_{datetime.now(timezone.utc).timestamp()}"
        
        try:
            # Create order using py-clob-client
            order = self.clob_client.create_order(
                token_id=token_id,
                price=float(price),
                size=float(size),
                side=side,
                order_type=order_type,
            )
            
            # Post order to CLOB
            result = self.clob_client.post_order(order)
            order_id = result.get("order_id", "")
            
            logger.info(f"✅ Placed {side} order: {order_id}")
            return order_id
            
        except Exception as e:
            logger.error(f"❌ Failed to create order: {e}")
            return None

    async def get_best_prices(
        self, token_ids: Tuple[str, str]
    ) -> Optional[Tuple[Decimal, Decimal]]:
        """
        Get best ask prices for both outcome tokens.
        
        Args:
            token_ids: (up_token_id, down_token_id)
            
        Returns:
            (best_ask_up, best_ask_down) or None
        """
        up_id, down_id = token_ids
        
        # Fetch both order books in parallel
        tasks = [
            self.get_order_book(up_id),
            self.get_order_book(down_id),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        book_up, book_down = results
        
        if isinstance(book_up, Exception) or not book_up:
            return None
        if isinstance(book_down, Exception) or not book_down:
            return None
        
        return (book_up.best_ask, book_down.best_ask)

    async def poll_markets_continuously(
        self,
        markets: List[MarketInfo],
        callback=None
    ):
        """
        Continuously poll order books for given markets.
        Call callback(market_id, up_price, down_price) when prices update.
        
        Args:
            markets: List of MarketInfo to monitor
            callback: Async callback function
        """
        while True:
            try:
                for market in markets:
                    if not market.is_active:
                        continue
                    
                    # Get prices for both legs
                    prices = await self.get_best_prices(
                        tuple(market.outcome_tokens[:2])
                    )
                    
                    if prices and callback:
                        up_price, down_price = prices
                        await callback(market.market_id, up_price, down_price)
                
                await asyncio.sleep(config.POLL_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ Error in polling loop: {e}")
                await asyncio.sleep(5)

    async def check_user_balance(self) -> Optional[Decimal]:
        """Get user's USDC balance on Polymarket."""
        if not self.clob_client:
            return None
        
        try:
            balance = self.clob_client.get_balance()
            return Decimal(str(balance))
        except Exception as e:
            logger.error(f"❌ Failed to get balance: {e}")
            return None

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders for the user."""
        if not self.clob_client:
            return []
        
        try:
            orders = self.clob_client.get_orders()
            return orders
        except Exception as e:
            logger.error(f"❌ Failed to get orders: {e}")
            return []

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order by ID."""
        if not self.clob_client:
            return False
        
        if config.DRY_RUN:
            logger.info(f"🌙 DRY_RUN: Would cancel order {order_id}")
            return True
        
        try:
            self.clob_client.cancel_order(order_id)
            logger.info(f"✅ Cancelled order: {order_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cancel order: {e}")
            return False
