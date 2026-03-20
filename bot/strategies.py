"""
Trading strategies for Polymarket BTC bot
"""
import logging
from decimal import Decimal
from typing import Dict, Optional

from polymarket import OrderBook
from config import config

logger = logging.getLogger(__name__)

class TradingStrategies:
    """Collection of trading strategies."""

    def __init__(self, polymarket_client, price_feed):
        self.pm_client = polymarket_client
        self.price_feed = price_feed

    async def check_arbitrage(self, market_id: str, orderbook: OrderBook) -> Optional[Dict]:
        """
        Check for risk-free arbitrage opportunity.
        If best_ask_up + best_ask_down < TARGET_SUM, place limit buys on both sides.
        """
        try:
            best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.pm_client.get_best_prices(orderbook)

            if not all([best_yes_ask, best_no_ask]):
                return None

            # Calculate sum of best asks
            ask_sum = best_yes_ask + best_no_ask

            if ask_sum < config.TARGET_SUM:
                # Arbitrage opportunity found
                edge = config.TARGET_SUM - ask_sum
                size = min(config.MAX_POSITION_SIZE, Decimal('10'))  # Conservative size

                opportunity = {
                    'type': 'arbitrage',
                    'market_id': market_id,
                    'yes_price': best_yes_ask,
                    'no_price': best_no_ask,
                    'sum': ask_sum,
                    'target': config.TARGET_SUM,
                    'edge': edge,
                    'size': size,
                    'expected_profit': edge * size * 2  # Profit from both legs
                }

                logger.info(f"🎯 Arbitrage opportunity: {ask_sum:.4f} < {config.TARGET_SUM} (edge: {edge:.4f})")
                return opportunity

        except Exception as e:
            logger.error(f"Arbitrage check failed: {e}")

        return None

    async def check_snipe(self, market_id: str, orderbook: OrderBook) -> Optional[Dict]:
        """
        Last-second sniping strategy using external BTC price momentum.
        """
        try:
            # Get current BTC price
            btc_price = await self.price_feed.get_btc_price()

            # Get market prices
            best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.pm_client.get_best_prices(orderbook)

            if not all([best_yes_bid, best_yes_ask]):
                return None

            # Simple momentum calculation (would need more sophisticated analysis)
            # For now, just check if implied probability deviates significantly from spot
            implied_prob = (best_yes_bid + best_yes_ask) / 2

            # This is a simplified version - real implementation would use
            # Monte Carlo simulations and more sophisticated momentum analysis
            if abs(implied_prob - Decimal('0.5')) > config.EDGE_THRESHOLD:
                direction = 'YES' if implied_prob > Decimal('0.5') else 'NO'
                price = best_yes_ask if direction == 'YES' else best_no_ask
                size = config.MAX_POSITION_SIZE

                opportunity = {
                    'type': 'snipe',
                    'market_id': market_id,
                    'direction': direction,
                    'price': price,
                    'size': size,
                    'edge': abs(implied_prob - Decimal('0.5')),
                    'btc_price': btc_price
                }

                logger.info(f"🎯 Sniping opportunity: {direction} at {price} (edge: {opportunity['edge']:.4f})")
                return opportunity

        except Exception as e:
            logger.error(f"Snipe check failed: {e}")

        return None

    async def check_momentum(self, market_id: str, orderbook: OrderBook) -> Optional[Dict]:
        """
        Momentum-based strategy using Bayesian probability analysis.
        """
        try:
            # This would implement more sophisticated momentum analysis
            # For now, simplified version
            best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.pm_client.get_best_prices(orderbook)

            if not all([best_yes_bid, best_yes_ask]):
                return None

            # Calculate market imbalance
            yes_volume = sum(size for _, size in orderbook.yes_bids[:5])
            no_volume = sum(size for _, size in orderbook.no_bids[:5])

            if yes_volume > no_volume * Decimal('1.5'):  # Strong bullish momentum
                opportunity = {
                    'type': 'momentum',
                    'market_id': market_id,
                    'direction': 'YES',
                    'price': best_yes_ask,
                    'size': config.MAX_POSITION_SIZE,
                    'confidence': min(yes_volume / no_volume, Decimal('3')),
                    'volume_ratio': yes_volume / no_volume
                }
                return opportunity

            elif no_volume > yes_volume * Decimal('1.5'):  # Strong bearish momentum
                opportunity = {
                    'type': 'momentum',
                    'market_id': market_id,
                    'direction': 'NO',
                    'price': best_no_ask,
                    'size': config.MAX_POSITION_SIZE,
                    'confidence': min(no_volume / yes_volume, Decimal('3')),
                    'volume_ratio': no_volume / yes_volume
                }
                return opportunity

        except Exception as e:
            logger.error(f"Momentum check failed: {e}")

        return None

    async def check_market_making(self, market_id: str, orderbook: OrderBook) -> Optional[Dict]:
        """
        Market making strategy with dynamic quoting.
        """
        try:
            best_yes_bid, best_yes_ask, best_no_bid, best_no_ask = self.pm_client.get_best_prices(orderbook)

            if not all([best_yes_bid, best_yes_ask, best_no_bid, best_no_ask]):
                return None

            # Calculate spread
            yes_spread = best_yes_ask - best_yes_bid
            no_spread = best_no_ask - best_no_bid

            # If spreads are too wide, provide liquidity
            if yes_spread > Decimal('0.05') or no_spread > Decimal('0.05'):
                size = config.MAX_POSITION_SIZE / Decimal('2')  # Smaller size for MM

                opportunity = {
                    'type': 'market_making',
                    'market_id': market_id,
                    'yes_bid_price': best_yes_bid + Decimal('0.001'),  # Slightly better than best bid
                    'yes_ask_price': best_yes_ask - Decimal('0.001'),  # Slightly better than best ask
                    'no_bid_price': best_no_bid + Decimal('0.001'),
                    'no_ask_price': best_no_ask - Decimal('0.001'),
                    'size': size,
                    'yes_spread': yes_spread,
                    'no_spread': no_spread
                }

                logger.info(f"🎯 Market making opportunity: spreads {yes_spread:.4f}/{no_spread:.4f}")
                return opportunity

        except Exception as e:
            logger.error(f"Market making check failed: {e}")

        return None

    async def execute_opportunity(self, opportunity: Dict) -> bool:
        """Execute a trading opportunity."""
        try:
            opp_type = opportunity['type']
            market_id = opportunity['market_id']

            if opp_type == 'arbitrage':
                # Place both legs of arbitrage
                success1 = await self.pm_client.place_limit_order(
                    market_id, 'YES', opportunity['yes_price'], opportunity['size']
                )
                success2 = await self.pm_client.place_limit_order(
                    market_id, 'NO', opportunity['no_price'], opportunity['size']
                )
                return success1 and success2

            elif opp_type in ['snipe', 'momentum']:
                # Place single leg order
                return await self.pm_client.place_limit_order(
                    market_id, opportunity['direction'],
                    opportunity['price'], opportunity['size']
                )

            elif opp_type == 'market_making':
                # Place multiple orders for market making
                # This is simplified - real MM would place multiple orders
                success1 = await self.pm_client.place_limit_order(
                    market_id, 'YES', opportunity['yes_bid_price'], opportunity['size']
                )
                success2 = await self.pm_client.place_limit_order(
                    market_id, 'NO', opportunity['no_bid_price'], opportunity['size']
                )
                return success1 and success2

            else:
                logger.warning(f"Unknown opportunity type: {opp_type}")
                return False

        except Exception as e:
            logger.error(f"Opportunity execution failed: {e}")
            return False