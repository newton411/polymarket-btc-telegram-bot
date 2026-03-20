"""
Utility functions for Polymarket trading bot
"""
import logging
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable
from functools import wraps

# Configure logging
def setup_logging(level=logging.INFO):
    """Setup comprehensive logging configuration."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log", mode='a')
        ]
    )

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

# Decimal utilities
def decimal_to_str(value: Decimal, precision: int = 4) -> str:
    """Convert Decimal to string with specified precision."""
    return f"{value:.{precision}f}"

def safe_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """Safely convert value to Decimal."""
    try:
        if isinstance(value, str):
            return Decimal(value)
        elif isinstance(value, (int, float)):
            return Decimal(str(value))
        elif isinstance(value, Decimal):
            return value
        else:
            return default
    except:
        return default

def round_decimal(value: Decimal, places: int = 4) -> Decimal:
    """Round Decimal to specified decimal places."""
    return value.quantize(Decimal('1e-{}'.format(places)), rounding=ROUND_HALF_UP)

# Retry decorator
def retry_on_failure(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retrying functions on failure."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            import logging

            logger = logging.getLogger(__name__)
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            return None
        return wrapper
    return decorator

# Performance tracking utilities
class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_second: float = 1.0):
        self.calls_per_second = calls_per_second
        self.last_call = 0.0

    async def wait_if_needed(self):
        """Wait if necessary to respect rate limit."""
        import time
        import asyncio

        current_time = time.time()
        time_since_last = current_time - self.last_call
        min_interval = 1.0 / self.calls_per_second

        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        self.last_call = time.time()

# Logging helpers
def log_trade(opportunity: dict, success: bool):
    """Log trade execution."""
    logger = logging.getLogger(__name__)

    if success:
        logger.info(
            f"TRADE EXECUTED: {opportunity['type'].upper()} | "
            f"Market: {opportunity['market_id'][:8]} | "
            f"Size: {opportunity.get('size', 'N/A')} | "
            f"Expected P&L: {opportunity.get('expected_profit', 'N/A')}"
        )
    else:
        logger.error(
            f"TRADE FAILED: {opportunity['type'].upper()} | "
            f"Market: {opportunity['market_id'][:8]}"
        )

def log_opportunity(opportunity: dict):
    """Log detected trading opportunity."""
    logger = logging.getLogger(__name__)

    if opportunity['type'] == 'arbitrage':
        logger.info(
            f"ARBITRAGE: Sum {opportunity['sum']:.4f} < {opportunity['target']:.4f} | "
            f"Edge: {opportunity['edge']:.4f} | Size: {opportunity['size']}"
        )
    elif opportunity['type'] in ['snipe', 'momentum']:
        logger.info(
            f"{opportunity['type'].upper()}: {opportunity['direction']} | "
            f"Price: {opportunity['price']:.4f} | Edge: {opportunity['edge']:.4f}"
        )
    elif opportunity['type'] == 'market_making':
        logger.info(
            f"MM OPPORTUNITY: Spreads {opportunity['yes_spread']:.4f}/{opportunity['no_spread']:.4f} | "
            f"Size: {opportunity['size']}"
        )

# Validation helpers
def validate_config():
    """Validate configuration values."""
    from config import config

    errors = []

    if config.TARGET_SUM <= 0 or config.TARGET_SUM >= 2:
        errors.append(f"TARGET_SUM must be between 0 and 2, got {config.TARGET_SUM}")

    if config.MAX_POSITION_SIZE <= 0:
        errors.append(f"MAX_POSITION_SIZE must be positive, got {config.MAX_POSITION_SIZE}")

    if config.EDGE_THRESHOLD < 0:
        errors.append(f"EDGE_THRESHOLD must be non-negative, got {config.EDGE_THRESHOLD}")

    if config.POLL_INTERVAL <= 0:
        errors.append(f"POLL_INTERVAL must be positive, got {config.POLL_INTERVAL}")

    if config.DAILY_DRAWDOWN_STOP <= 0 or config.DAILY_DRAWDOWN_STOP > 1:
        errors.append(f"DAILY_DRAWDOWN_STOP must be between 0 and 1, got {config.DAILY_DRAWDOWN_STOP}")

    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(errors))

    print("✅ Configuration validation passed")

# Environment helpers
def load_env_file():
    """Load environment variables from .env file."""
    from dotenv import load_dotenv
    import os

    # Try to load from bot/.env first, then root .env
    if os.path.exists('.env'):
        load_dotenv('.env')
    elif os.path.exists('../.env'):
        load_dotenv('../.env')

    print("✅ Environment variables loaded")

# Cleanup helpers
def cleanup_resources(*resources):
    """Cleanup multiple resources."""
    import logging
    logger = logging.getLogger(__name__)

    for resource in resources:
        try:
            if hasattr(resource, 'close'):
                if asyncio.iscoroutinefunction(resource.close):
                    asyncio.create_task(resource.close())
                else:
                    resource.close()
            elif hasattr(resource, 'stop'):
                if asyncio.iscoroutinefunction(resource.stop):
                    asyncio.create_task(resource.stop())
                else:
                    resource.stop()
        except Exception as e:
            logger.error(f"Error cleaning up resource: {e}")