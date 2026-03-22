"""
Trading Strategies for RecondTrade Bot
Primary Strategy: Dynamic Sum Arbitrage (mathematically risk-free)

Strategy Logic:
- Monitor 5-minute BTC Up/Down markets
- Trigger when best_ask_UP + best_ask_DOWN <= TARGET_SUM (0.95)
- Add momentum filter: check Binance BTC spot for extreme reversals (30s window)
- Place limit buys on both legs: size=25 shares, post-only
- Lock in guaranteed profit: 25 × (1 - 0.95) = $1.25 per fill
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Callable
import ccxt

from config import config
from polymarket_client import PolymarketClient, MarketInfo, OrderBookSnapshot

logger = logging.getLogger(__name__)


@dataclass
class OpportunityDetected:
    """An arbitrage opportunity discovered by the strategy"""
    market_id: str
    market_title: str
    best_ask_up: Decimal
    best_ask_down: Decimal
    sum_price: Decimal
    edge: Decimal  # Profit margin = 1 - sum_price
    token_id_up: str
    token_id_down: str
    up_size: Decimal = Decimal("25")  # Fixed size
    down_size: Decimal = Decimal("25")
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MomentumState:
    """Recent price history for momentum analysis"""
    prices: List[Decimal] = field(default_factory=list)
    timestamps: List[datetime] = field(default_factory=list)
    max_lookback_seconds: int = 30


class BinancePriceFeed:
    """Subscribe to Binance BTC/USDT spot price updates"""

    def __init__(self):
        self.exchange = ccxt.binance()
        self.latest_price: Optional[Decimal] = None
        self.latest_price_time: Optional[datetime] = None
        self.momentum = MomentumState(max_lookback_seconds=30)

    async def initialize(self):
        """Initialize and start polling Binance."""
        await self.update_price()

    async def update_price(self):
        """Fetch latest BTC/USDT price from Binance."""
        try:
            ticker = await asyncio.to_thread(
                self.exchange.fetch_ticker,
                config.BINANCE_SYMBOL
            )
            self.latest_price = Decimal(str(ticker["last"]))
            self.latest_price_time = datetime.now(timezone.utc)

            # Track price history for momentum
            self.momentum.prices.append(self.latest_price)
            self.momentum.timestamps.append(self.latest_price_time)

            # Prune old prices (keep only last 30s)
            cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=self.momentum.max_lookback_seconds
            )
            valid_indices = [
                i
                for i, t in enumerate(self.momentum.timestamps)
                if t > cutoff
            ]
            if valid_indices:
                self.momentum.prices = [
                    self.momentum.prices[i] for i in valid_indices
                ]
                self.momentum.timestamps = [
                    self.momentum.timestamps[i] for i in valid_indices
                ]

        except Exception as e:
            logger.warning(f"⚠️  Failed to fetch Binance price: {e}")

    async def poll_continuously(self, interval_seconds: float = 1.0):
        """Continuously update Binance price."""
        while True:
            await self.update_price()
            await asyncio.sleep(interval_seconds)

    def check_no_extreme_reversal(self, threshold_percent: float = 5.0) -> bool:
        """
        Check if there was NO extreme price reversal in the last 30s.
        This is a momentum filter to avoid trading before sudden reversals.

        Args:
            threshold_percent: Reversal threshold (default 5%)

        Returns:
            True if safe to trade (no extreme reversal), False otherwise
        """
        if len(self.momentum.prices) < 2:
            return True  # Not enough data, allow trade

        min_price = min(self.momentum.prices)
        max_price = max(self.momentum.prices)

        if min_price == 0:
            return True

        reversal_pct = ((max_price - min_price) / min_price) * Decimal("100")
        has_reversal = reversal_pct > Decimal(threshold_percent)

        if has_reversal:
            logger.info(
                f"⚠️  Momentum filter: Extreme reversal detected ({reversal_pct:.2f}%) - skip trade"
            )
            return False

        return True  # No extreme reversal, safe to trade


class TradingStrategies:
    """
    Strategy engine managing Dynamic Sum Arbitrage.
    Detects opportunities, filters with momentum, and triggers orders.
    """

    def __init__(self, clob_client: PolymarketClient):
        self.clob = clob_client
        self.binance = BinancePriceFeed()
        self.active_markets: List[MarketInfo] = []
        self.opportunities: List[OpportunityDetected] = []
        self.opportunity_callbacks: List[Callable] = []

    async def initialize(self):
        """Initialize strategy engine."""
        await self.binance.initialize()
        logger.info("✅ Trading strategy engine initialized")

    async def register_opportunity_callback(self, callback: Callable):
        """Register callback to be called when opportunity is detected."""
        self.opportunity_callbacks.append(callback)

    async def run_detection_loop(self):
        """
        Main loop: monitor markets, detect opportunities, trigger callbacks.
        Runs continuously in background.
        """
        while True:
            try:
                # Discover markets if not already discovered
                if not self.active_markets:
                    logger.info("🔍 Discovering BTC 5-min markets...")
                    self.active_markets = await self.clob.discover_markets()

                # Check each market for opportunities
                for market in self.active_markets:
                    if not market.is_active:
                        continue

                    # Get prices for both legs
                    prices = await self.clob.get_best_prices(
                        tuple(market.outcome_tokens[:2])
                    )
                    if not prices:
                        continue

                    best_ask_up, best_ask_down = prices
                    sum_price = best_ask_up + best_ask_down
                    edge = Decimal("1") - sum_price

                    # ───────────────────────────────────────────────────────
                    # CHECK: Is sum <= target threshold?
                    # ───────────────────────────────────────────────────────
                    if sum_price > config.ARB_SUM_TARGET:
                        continue  # Not attractive

                    # ───────────────────────────────────────────────────────
                    # CHECK: Momentum filter (no extreme reversals)
                    # ───────────────────────────────────────────────────────
                    if not self.binance.check_no_extreme_reversal():
                        logger.debug(f"Skipping {market.title} - momentum filter")
                        continue

                    # ───────────────────────────────────────────────────────
                    # CHECK: Minimum edge threshold
                    # ───────────────────────────────────────────────────────
                    if edge < config.EDGE_THRESHOLD:
                        continue

                    # Opportunity found!
                    opp = OpportunityDetected(
                        market_id=market.market_id,
                        market_title=market.title,
                        best_ask_up=best_ask_up,
                        best_ask_down=best_ask_down,
                        sum_price=sum_price,
                        edge=edge,
                        token_id_up=market.outcome_tokens[0],
                        token_id_down=market.outcome_tokens[1],
                    )

                    logger.info(
                        f"🎯 OPPORTUNITY DETECTED:\n"
                        f"  Market: {market.title}\n"
                        f"  Sum: {sum_price:.4f} (target: {config.ARB_SUM_TARGET})\n"
                        f"  Edge: {edge*100:.2f}%\n"
                        f"  Profit per fill: ${Decimal('25') * edge:.2f}"
                    )

                    # Call all registered callbacks
                    for callback in self.opportunity_callbacks:
                        try:
                            await callback(opp)
                        except Exception as e:
                            logger.error(f"❌ Callback error: {e}")

                    # Store in history
                    self.opportunities.append(opp)
                    if len(self.opportunities) > 1000:
                        self.opportunities = self.opportunities[-1000:]

                # Poll interval
                await asyncio.sleep(config.POLL_INTERVAL)

            except Exception as e:
                logger.error(f"❌ Error in detection loop: {e}")
                await asyncio.sleep(5)

    async def place_arbitrage_orders(self, opportunity: OpportunityDetected) -> bool:
        """
        Execute a discovered arbitrage opportunity.
        Place limit buy orders on both legs.

        Args:
            opportunity: OpportunityDetected to execute

        Returns:
            True if both orders placed successfully
        """
        logger.info(
            f"💰 Executing arbitrage: {opportunity.market_title}\n"
            f"   BUY 25 UP @ ${opportunity.best_ask_up}\n"
            f"   BUY 25 DOWN @ ${opportunity.best_ask_down}\n"
            f"   Total spend: ${opportunity.up_size * opportunity.best_ask_up + opportunity.down_size * opportunity.best_ask_down:.2f}\n"
            f"   Expected profit: ${opportunity.up_size * opportunity.edge:.2f}"
        )

        # Place orders in parallel
        tasks = [
            self.clob.create_order(
                token_id=opportunity.token_id_up,
                side="BUY",
                size=opportunity.up_size,
                price=opportunity.best_ask_up,
                order_type="GTC",  # Good-Till-Cancel
            ),
            self.clob.create_order(
                token_id=opportunity.token_id_down,
                side="BUY",
                size=opportunity.down_size,
                price=opportunity.best_ask_down,
                order_type="GTC",
            ),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check if both orders succeeded
        order_ids = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Order {i+1} failed: {result}")
                return False
            if not result:
                logger.error(f"❌ Order {i+1} returned None")
                return False
            order_ids.append(result)

        logger.info(f"✅ Both orders placed: {order_ids}")
        return True

    async def start_background_tasks(self):
        """Start all background monitoring tasks."""
        # Start Binance price feed
        asyncio.create_task(self.binance.poll_continuously(interval_seconds=1.0))
        # Start opportunity detection
        asyncio.create_task(self.run_detection_loop())

        logger.info("🚀 Background tasks started")