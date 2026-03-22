"""
RecondTrade Bot — Configuration and environment loading for Polymarket BTC Trading
Pure Python 3.11+ asyncio Telegram bot
"""
import os
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Config:
    """
    Central configuration management.
    All settings loaded from environment variables with sensible defaults.
    """

    # ────────────────────────────────────────────────────────────────────────
    # POLYMARKET & CLOB CREDENTIALS
    # ────────────────────────────────────────────────────────────────────────
    POLYMARKET_PRIVATE_KEY: Optional[str] = os.getenv("POLYMARKET_PRIVATE_KEY")
    POLYMARKET_ADDRESS: Optional[str] = os.getenv("POLYMARKET_ADDRESS")

    # CLOB API endpoints
    CLOB_HOST: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
    GAMMA_API_BASE: str = os.getenv("GAMMA_API_BASE", "https://gamma-api.polymarket.com")

    # ────────────────────────────────────────────────────────────────────────
    # TELEGRAM BOT
    # ────────────────────────────────────────────────────────────────────────
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    ALLOWED_USER_ID: Optional[int] = (
        int(os.getenv("ALLOWED_USER_ID"))
        if os.getenv("ALLOWED_USER_ID")
        else None
    )

    # ────────────────────────────────────────────────────────────────────────
    # TRADING CONFIGURATION
    # ────────────────────────────────────────────────────────────────────────
    # DRY_RUN = True: detect opportunities, print logs, DON'T place orders
    # DRY_RUN = False: place actual orders on Polymarket
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    # Sum arbitrage: trigger when best_ask_UP + best_ask_DOWN <= TARGET_SUM
    ARB_SUM_TARGET: Decimal = Decimal(os.getenv("ARB_SUM_TARGET", "0.95"))

    # Maximum position size per trade leg (in USD)
    MAX_POSITION_USD: Decimal = Decimal(os.getenv("MAX_POSITION_USD", "50"))

    # Daily drawdown stop-loss (10% = 0.10)
    DAILY_DRAWDOWN_STOP: Decimal = Decimal(os.getenv("DAILY_DRAWDOWN_STOP", "0.10"))

    # Minimum edge to trigger trade (2% = 0.02)
    EDGE_THRESHOLD: Decimal = Decimal(os.getenv("EDGE_THRESHOLD", "0.02"))

    # ────────────────────────────────────────────────────────────────────────
    # POLLING & UPDATES
    # ────────────────────────────────────────────────────────────────────────
    # Poll order books every N seconds
    POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "2.0"))

    # Update Telegram dashboard every N seconds
    DASHBOARD_UPDATE_INTERVAL: int = int(os.getenv("DASHBOARD_UPDATE_INTERVAL", "15"))

    # Max trades per hour (safety limit)
    MAX_TRADES_PER_HOUR: int = int(os.getenv("MAX_TRADES_PER_HOUR", "300"))

    # ────────────────────────────────────────────────────────────────────────
    # MARKET DISCOVERY
    # ────────────────────────────────────────────────────────────────────────
    BTC_MARKET_FILTER: str = "bitcoin"  # Search for BTC markets in Gamma API
    RESOLUTION_FILTER: str = "5m"  # Only 5-minute resolution markets

    # ────────────────────────────────────────────────────────────────────────
    # PRICE FEED (Binance for momentum filter)
    # ────────────────────────────────────────────────────────────────────────
    BINANCE_SYMBOL: str = "BTC/USDT"  # Binance spot trading pair
    MOMENTUM_WINDOW_SECONDS: int = 30  # Look back 30s for reversal detection

    # ────────────────────────────────────────────────────────────────────────
    # DATABASE
    # ────────────────────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DB_PATH", "./bot/data.db")
    POINTS_DB_PATH: str = os.getenv("POINTS_DB_PATH", "./bot/points.db")

    # ────────────────────────────────────────────────────────────────────────
    # CREATOR WALLET (for TGE allocation tracking)
    # ────────────────────────────────────────────────────────────────────────
    CREATOR_WALLET: str = "0x74299c15CcEf4b48B06633E44F4F131209E0d233"

    # ────────────────────────────────────────────────────────────────────────
    # POLYGON BLOCKCHAIN (for subscription verification)
    # ────────────────────────────────────────────────────────────────────────
    POLYGON_RPC: str = os.getenv(
        "POLYGON_RPC",
        "https://polygon-rpc.com"
    )
    POLYGON_CHAIN_ID: int = 137  # Polygon mainnet
    USDC_POLYGON_ADDRESS: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

    # ────────────────────────────────────────────────────────────────────────
    # PRO SUBSCRIPTION
    # ────────────────────────────────────────────────────────────────────────
    PRO_SUBSCRIPTION_COST_USDC: Decimal = Decimal("10")  # 10 USDC = Pro for 30 days
    PRO_SUBSCRIPTION_DURATION_DAYS: int = 30

    # ────────────────────────────────────────────────────────────────────────
    # POINTS SYSTEM
    # ────────────────────────────────────────────────────────────────────────
    POINTS_PER_START: int = 50  # /start command
    POINTS_PER_STATUS: int = 10  # /status command
    POINTS_PER_DETECTED_TRADE: int = 25  # When bot detects opportunity
    POINTS_PER_HIGH_EDGE: int = 100  # Edge > 5%
    PRO_MULTIPLIER: float = 2.0  # Pro users earn 2× points

    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is set."""
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("❌ TELEGRAM_TOKEN is required in .env")

        if not cls.DRY_RUN:
            # Live trading requires Polymarket credentials
            if not cls.POLYMARKET_PRIVATE_KEY:
                raise ValueError("❌ POLYMARKET_PRIVATE_KEY required for live trading (DRY_RUN=false)")
            if not cls.POLYMARKET_ADDRESS:
                raise ValueError("❌ POLYMARKET_ADDRESS required for live trading")
            if not cls.ALLOWED_USER_ID:
                raise ValueError("❌ ALLOWED_USER_ID required for live trading (security)")

        # Print startup banner
        print("\n" + "="*70)
        print("🤖 RecondTrade Bot — Dynamic Sum Arbitrage")
        print("="*70)
        print(f"🔐 Mode: {'🟢 DRY-RUN (no real orders)' if cls.DRY_RUN else '🔴 LIVE TRADING (real orders)'}")
        print(f"💰 Target Sum: {cls.ARB_SUM_TARGET} (5% locked edge)")
        print(f"📊 Max Position: ${cls.MAX_POSITION_USD} per leg")
        print(f"⏱️  Poll Interval: {cls.POLL_INTERVAL}s")
        print(f"🎲 Dashboard Update: {cls.DASHBOARD_UPDATE_INTERVAL}s")
        print(f"🔑 Creator Wallet: {cls.CREATOR_WALLET}")
        print("="*70 + "\n")


# Global config instance
config = Config()