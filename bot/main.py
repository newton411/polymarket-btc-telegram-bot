"""
RecondTrade Bot — Main Entry Point
Production-ready Polymarket BTC arbitrage bot using Dynamic Sum strategy
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from config import config
from polymarket_client import PolymarketClient
from strategies import TradingStrategies
from telegram_bot import TelegramBot
from points_manager import PointsManager
from subscription import SubscriptionManager
from utils import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


class RecondTradeBot:
    """Main bot orchestrator."""

    def __init__(self):
        self.running = False
        self.clob_client = PolymarketClient()
        self.strategies = TradingStrategies(self.clob_client)
        self.points_manager = PointsManager()
        self.subscription_manager = SubscriptionManager(self.points_manager)
        self.telegram_bot = TelegramBot(
            self.clob_client,
            self.strategies,
            self.points_manager,
            self.subscription_manager,
        )

    async def initialize(self):
        """Initialize all components."""
        logger.info("🚀 RecondTrade Bot Initializing...")
        
        # Validate config
        try:
            config.validate()
        except ValueError as e:
            logger.error(f"❌ Config validation failed: {e}")
            sys.exit(1)
        
        # Initialize Polymarket client
        await self.clob_client.initialize()
        logger.info("✅ Polymarket CLOB client initialized")
        
        # Initialize strategy engine
        await self.strategies.initialize()
        logger.info("✅ Trading strategy engine initialized")
        
        # Initialize subscription manager
        await self.subscription_manager.initialize()
        logger.info("✅ Subscription manager initialized")
        
        # Register opportunity callback
        await self.strategies.register_opportunity_callback(self.on_opportunity)
        
        # Start background tasks
        await self.strategies.start_background_tasks()
        
        logger.info("✅ All components initialized")

    async def on_opportunity(self, opportunity):
        """Handle detected trading opportunity."""
        logger.info(
            f"🎯 OPPORTUNITY DETECTED:\n"
            f"  Market: {opportunity.market_title}\n"
            f"  Sum: {opportunity.sum_price:.4f}\n"
            f"  Edge: {opportunity.edge * 100:.2f}%\n"
            f"  Profit: ${opportunity.up_size * opportunity.edge:.2f}"
        )
        
        # Try to execute
        if not config.DRY_RUN:
            success = await self.strategies.place_arbitrage_orders(opportunity)
            if success:
                logger.info("✅ Orders placed successfully")
            else:
                logger.warning("❌ Failed to place orders")
        
        # Award points to users
        for user_id in self.telegram_bot.user_sessions:
            self.points_manager.record_trade(
                user_id,
                opportunity.market_id,
                opportunity.edge,
                pnl=opportunity.up_size * opportunity.edge
            )
        
        # Send notification to Telegram
        await self.telegram_bot.on_opportunity(opportunity)

    async def run(self):
        """Main bot run loop."""
        self.running = True
        logger.info("🚀 RecondTrade Bot started\n")
        
        # Start Telegram bot
        await self.telegram_bot.run()
        
        # Main loop
        try:
            while self.running:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("⏹️ Shutdown signal received")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}", exc_info=True)
            self.running = False

    async def shutdown(self):
        """Clean shutdown."""
        logger.info("🛑 Shutting down RecondTrade Bot...")
        
        self.running = False
        
        # Stop Telegram bot
        try:
            await self.telegram_bot.stop()
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}")
        
        # Close Polymarket client
        try:
            await self.clob_client.close()
        except Exception as e:
            logger.error(f"Error closing CLOB client: {e}")
        
        # Close subscription manager
        try:
            await self.subscription_manager.close()
        except Exception as e:
            logger.error(f"Error closing subscription manager: {e}")
        
        logger.info("✅ Graceful shutdown complete")


async def main():
    """Main entry point."""
    bot = RecondTradeBot()
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Signal {signum} received")
        asyncio.create_task(bot.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.initialize()
        await bot.run()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Stopped")
        sys.exit(0)
