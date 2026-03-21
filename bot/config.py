"""
Configuration and environment loading for Polymarket BTC Trading Bot
"""
import os
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Core Configuration
class Config:
    """Central configuration management."""

    # Polymarket API
    POLYMARKET_PRIVATE_KEY: Optional[str] = os.getenv("POLYMARKET_PRIVATE_KEY")
    POLYMARKET_ADDRESS: Optional[str] = os.getenv("POLYMARKET_ADDRESS")

    # Telegram Bot
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "8707545048:AAF2XduF-CJQ1pH5Ipqmdjl3riVe82S0toE")
    ALLOWED_USER_ID: Optional[int] = int(os.getenv("ALLOWED_USER_ID", "0")) if os.getenv("ALLOWED_USER_ID") else None

    # Trading Configuration
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    TARGET_SUM: Decimal = Decimal(os.getenv("TARGET_SUM", "0.96"))  # For arbitrage
    MAX_POSITION_SIZE: Decimal = Decimal(os.getenv("MAX_POSITION_SIZE", "20.0"))  # USD per leg
    DAILY_DRAWDOWN_STOP: Decimal = Decimal(os.getenv("DAILY_DRAWDOWN_STOP", "0.10"))  # 10%

    # Timing
    POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "3.0"))  # seconds
    DASHBOARD_UPDATE_INTERVAL: int = int(os.getenv("DASHBOARD_UPDATE_INTERVAL", "30"))  # seconds

    # Risk Management
    EDGE_THRESHOLD: Decimal = Decimal(os.getenv("EDGE_THRESHOLD", "0.02"))  # Minimum edge to trade
    MAX_TRADES_PER_HOUR: int = int(os.getenv("MAX_TRADES_PER_HOUR", "300"))

    # Market Discovery
    GAMMA_API_BASE: str = "https://gamma-api.polymarket.com"
    BTC_MARKET_FILTER: str = "bitcoin"
    RESOLUTION_FILTER: str = "5m"

    # CLOB Configuration
    CLOB_HOST: str = "https://clob.polymarket.com"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN is required")

        if not cls.DRY_RUN:
            if not cls.POLYMARKET_PRIVATE_KEY:
                raise ValueError("POLYMARKET_PRIVATE_KEY is required for live trading")
            if not cls.POLYMARKET_ADDRESS:
                raise ValueError("POLYMARKET_ADDRESS is required for live trading")
            if not cls.ALLOWED_USER_ID:
                raise ValueError("ALLOWED_USER_ID is required for live trading")

        print("⚠️  DRY_RUN MODE ENABLED - No real orders will be placed" if cls.DRY_RUN else "🔴 LIVE TRADING MODE - Real orders will be placed")
        print(f"🎯 Target Sum: {cls.TARGET_SUM}")
        print(f"📊 Max Position Size: ${cls.MAX_POSITION_SIZE}")
        print(f"⏱️  Poll Interval: {cls.POLL_INTERVAL}s")

# Global config instance
config = Config()