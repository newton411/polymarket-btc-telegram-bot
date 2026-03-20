#!/usr/bin/env python3
"""
Comprehensive system test for the Polymarket BTC Telegram Bot
"""
import asyncio
import sys
import os

# Add bot directory to path
sys.path.insert(0, os.path.dirname(__file__))

from main import TradingBot, PriceFeed

async def comprehensive_test():
    print('=== COMPREHENSIVE SYSTEM TEST ===')

    # Test PriceFeed
    print('1. Testing PriceFeed...')
    feed = PriceFeed()
    try:
        price = await feed.get_btc_price()
        print(f'   ✓ BTC Price: ${float(price):,.2f}')
    except Exception as e:
        print(f'   ✗ Price feed failed: {e}')
    finally:
        await feed.close()

    # Test Bot Initialization
    print('2. Testing Bot Initialization...')
    try:
        bot = TradingBot()
        print('   ✓ Bot initialized successfully')
        print(f'   ✓ Telegram token: {"Loaded" if bot.telegram_token else "Missing"}')
        strategies_count = sum([bot.enable_arbitrage, bot.enable_oracle_snipe,
                               bot.enable_momentum, bot.enable_cross_market, bot.enable_asymmetric])
        print(f'   ✓ Strategies: {strategies_count} enabled')
    except Exception as e:
        print(f'   ✗ Bot initialization failed: {e}')

    # Test Polymarket API (without credentials)
    print('3. Testing Polymarket API connectivity...')
    try:
        import requests
        response = requests.get('https://gamma-api.polymarket.com/markets',
                              params={'active': 'true', 'limit': 1},
                              timeout=5)
        if response.status_code == 200:
            print('   ✓ Polymarket API reachable')
        else:
            print(f'   ✗ Polymarket API returned {response.status_code}')
    except Exception as e:
        print(f'   ✗ Polymarket API test failed: {e}')

    print('=== TEST COMPLETE ===')

if __name__ == "__main__":
    asyncio.run(comprehensive_test())