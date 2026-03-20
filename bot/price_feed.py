"""
Price feed system with Binance primary and Kraken fallback
"""
import logging
from decimal import Decimal
from datetime import datetime, timezone

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

class PriceFeed:
    """Multi-provider price feed with fallbacks."""

    def __init__(self):
        self.primary_exchange = ccxt.binance({"enableRateLimit": True})
        self.fallback_exchange = ccxt.kraken({"enableRateLimit": True})
        self.last_price = Decimal("0.0")
        self.last_update = None

    async def get_btc_price(self) -> Decimal:
        """Get BTC price with fallback providers."""
        try:
            # Try primary provider (Binance)
            ticker = await self.primary_exchange.fetch_ticker("BTC/USDT")
            price = Decimal(str(ticker["last"]))
            self.last_price = price
            self.last_update = datetime.now(timezone.utc)
            return price
        except Exception as e:
            logger.warning(f"Primary price feed failed: {e}")
            try:
                # Try fallback provider (Kraken)
                ticker = await self.fallback_exchange.fetch_ticker("BTC/USD")
                price = Decimal(str(ticker["last"]))
                self.last_price = price
                self.last_update = datetime.now(timezone.utc)
                logger.info("Using fallback price feed (Kraken)")
                return price
            except Exception as e2:
                logger.error(f"Fallback price feed also failed: {e2}")
                # Return last known price if both fail
                if self.last_price > 0:
                    logger.warning("Using stale price data")
                    return self.last_price
                raise RuntimeError("All price feeds failed")

    async def close(self):
        """Close exchange connections."""
        await self.primary_exchange.close()
        await self.fallback_exchange.close()