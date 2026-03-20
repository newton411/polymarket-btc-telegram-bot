import asyncio
import os
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, symbol='BTC/USDT', timeframe='1m', limit=500):
        self.symbol = symbol
        self.timeframe = timeframe
        self.limit = limit
        self.binance = ccxt.binance()
        
        # Strategy Parameters (matches bot/main.py)
        self.edge_threshold = Decimal("0.10")
        self.stop_loss_pct = Decimal("0.05")
        self.take_profit_pct = Decimal("0.15")
        self.sigma_proxy = Decimal("100.0")
        
        # Performance Metrics
        self.total_pnl = Decimal("0.0")
        self.trades_count = 0
        self.wins = 0
        self.losses = 0
        self.initial_balance = Decimal("1000.0")
        self.balance = self.initial_balance

    async def fetch_historical_data(self):
        logger.info(f"Fetching {self.limit} candles for {self.symbol} ({self.timeframe})...")
        ohlcv = await self.binance.fetch_ohlcv(self.symbol, self.timeframe, limit=self.limit)
        await self.binance.close()
        return ohlcv

    def calculate_probability(self, btc_price, strike, time_left_seconds):
        # Bayesian Implied Probability Approximation
        time_factor = Decimal(str(max(0.1, time_left_seconds / 300.0))).sqrt()
        z_score = (btc_price - strike) / (self.sigma_proxy * time_factor)
        expected_prob = Decimal("0.5") + (z_score / Decimal("2.0"))
        return max(Decimal("0.01"), min(Decimal("0.99"), expected_prob))

    async def run(self):
        data = await self.fetch_historical_data()
        
        # Simulate 5-min markets resolve every 5th minute
        # We take chunks of 5 minutes and simulate strategy entry in first 2 mins
        
        active_positions = [] # [{market_strike, side, entry_price, entry_btc}]
        
        for i in range(len(data)):
            timestamp, open_p, high, low, close, vol = data[i]
            current_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            btc_price = Decimal(str(close))
            
            # 1. Resolve/Manage Existing Positions
            to_remove = []
            for pos in active_positions:
                time_passed = (current_time - pos['entry_time']).total_seconds()
                time_left = 300 - time_passed
                
                if time_left <= 0:
                    # Resolution
                    is_win = (btc_price > pos['strike'] and pos['side'] == 'YES') or (btc_price < pos['strike'] and pos['side'] == 'NO')
                    pnl = Decimal("10.0") * (Decimal("1.0") - pos['entry_price']) if is_win else Decimal("-10.0") * pos['entry_price']
                    self.total_pnl += pnl
                    self.balance += pnl
                    self.trades_count += 1
                    if is_win: self.wins += 1
                    else: self.losses += 1
                    to_remove.append(pos)
                    continue
                
                # SL/TP Check
                curr_prob = self.calculate_probability(btc_price, pos['strike'], time_left)
                market_price = curr_prob if pos['side'] == 'YES' else (1 - curr_prob)
                
                if market_price < pos['entry_price'] * (1 - self.stop_loss_pct):
                    pnl = Decimal("10.0") * (market_price - pos['entry_price'])
                    self.total_pnl += pnl
                    self.balance += pnl
                    self.trades_count += 1
                    self.losses += 1
                    to_remove.append(pos)
                elif market_price > pos['entry_price'] + (1 - pos['entry_price']) * self.take_profit_pct:
                    pnl = Decimal("10.0") * (market_price - pos['entry_price'])
                    self.total_pnl += pnl
                    self.balance += pnl
                    self.trades_count += 1
                    self.wins += 1
                    to_remove.append(pos)

            for p in to_remove: active_positions.remove(p)

            # 2. Check for New Opportunity (Simulation: every 5 minutes we 'discover' a new market)
            if i % 5 == 0:
                # Mock a market with strike near current price
                market_strike = Decimal(str(round(float(btc_price) / 100) * 100)) # Round to nearest 100
                time_left = 300 # 5 mins
                
                prob_yes = self.calculate_probability(btc_price, market_strike, time_left)
                # Assume market price is prob - spread
                price_yes = prob_yes - Decimal("0.05")
                price_no = (1 - prob_yes) - Decimal("0.05")
                
                if (prob_yes - price_yes) > self.edge_threshold:
                    active_positions.append({
                        'strike': market_strike,
                        'side': 'YES',
                        'entry_price': price_yes,
                        'entry_time': current_time,
                        'type': 'BUY'
                    })
                elif ((1 - prob_yes) - price_no) > self.edge_threshold:
                    active_positions.append({
                        'strike': market_strike,
                        'side': 'NO',
                        'entry_price': price_no,
                        'entry_time': current_time,
                        'type': 'BUY'
                    })

        self.report()

    def report(self):
        win_rate = (self.wins / self.trades_count * 100) if self.trades_count > 0 else 0
        roi = (self.total_pnl / self.initial_balance) * 100
        
        print("\n" + "="*30)
        print("📊 BACKTEST RESULTS")
        print("="*30)
        print(f"Symbol:         {self.symbol}")
        print(f"Initial Bal:    ${self.initial_balance}")
        print(f"Final Bal:      ${self.balance:.2f}")
        print(f"Total PnL:      ${self.total_pnl:.2f} ({roi:.2f}%)")
        print(f"Trades:         {self.trades_count}")
        print(f"Win Rate:       {win_rate:.2f}%")
        print(f"Wins/Losses:    {self.wins}/{self.losses}")
        print("="*30 + "\n")

if __name__ == "__main__":
    backtester = Backtester(limit=1000)
    asyncio.run(backtester.run())
