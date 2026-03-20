import asyncio
import os
import logging
import json
import requests
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Polymarket official SDK
# Note: In a real environment, you'd run `pip install py-clob-client`
try:
    from clob_client.client import ClobClient
    from clob_client.clob_types import OrderArgs, ApiCredential
    from clob_client.constants import POLYGON
except ImportError:
    # Fallback for environment where library isn't installed yet
    ClobClient = None
    logger.warning("clob_client not found. Trading will be simulated.")

# Telegram bot library
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Price feed
import ccxt.async_support as ccxt

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class TradingBot:
    def __init__(self):
        # Configuration
        self.mode = os.getenv("TRADING_MODE", "DRY_RUN")
        self.edge_threshold = Decimal(os.getenv("EDGE_THRESHOLD", "0.10"))
        self.max_position_size = Decimal(os.getenv("MAX_POSITION_SIZE", "10.0")) # Smaller for safety
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_user_id = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
        
        # State
        self.is_paused = False
        self.stats = {
            "balance": Decimal("0.0"),
            "positions_count": 0,
            "net_delta": Decimal("0.0"),
            "trades_last_hour": 0,
            "win_rate": 0.0,
            "avg_edge": Decimal("0.0"),
            "pnl_today": Decimal("0.0"),
            "total_pnl": Decimal("0.0"),
            "last_logs": []
        }
        self.active_markets = {}  # { market_id: market_info }
        self.btc_price = Decimal("0.0")
        self.dashboard_message_id = None
        self.last_dashboard_update = 0
        
        # Clients
        self.clob_client = None
        self.binance = ccxt.binance()
        
    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.stats["last_logs"].append(log_entry)
        if len(self.stats["last_logs"]) > 5:
            self.stats["last_logs"].pop(0)
        logger.info(message)

    async def init_polymarket(self):
        try:
            if not ClobClient:
                self.add_log("SDK not installed. Running in simulation mode.")
                return False
                
            pk = os.getenv("POLYMARKET_PK")
            address = os.getenv("POLYMARKET_ADDRESS")
            key = os.getenv("POLYMARKET_API_KEY")
            passphrase = os.getenv("POLYMARKET_API_PASSPHRASE")
            secret = os.getenv("POLYMARKET_API_SECRET")
            
            if not pk or not address:
                self.add_log("Polymarket credentials missing. Simulating trades.")
                return False
            
            creds = ApiCredential(key=key, passphrase=passphrase, secret=secret)
            self.clob_client = ClobClient(
                "https://clob.polymarket.com",
                key=pk,
                chain_id=POLYGON,
                funder=address,
                creds=creds
            )
            self.add_log(f"Polymarket SDK connected (Mode: {self.mode})")
            return True
        except Exception as e:
            self.add_log(f"Polymarket init failed: {str(e)}")
            return False

    async def price_feed_loop(self):
        while True:
            try:
                ticker = await self.binance.fetch_ticker('BTC/USDT')
                self.btc_price = Decimal(str(ticker['last']))
                await asyncio.sleep(1) # Faster updates
            except Exception as e:
                self.add_log(f"Price feed error: {str(e)}")
                await asyncio.sleep(5)

    async def market_discovery_loop(self):
        gamma_api_url = "https://gamma-api.polymarket.com/markets"
        while True:
            try:
                # Query Gamma for 5-min BTC markets
                params = {
                    "active": "true",
                    "closed": "false",
                    "query": "Bitcoin 5 minutes"
                }
                response = requests.get(gamma_api_url, params=params)
                if response.status_code == 200:
                    markets = response.json()
                    new_markets = {}
                    for m in markets:
                        if "Bitcoin" in m.get("title", "") and "5 minutes" in m.get("title", ""):
                            # Extract strike and resolution time
                            # Title usually: "Will Bitcoin be above $68,500 at 12:00 PM?"
                            new_markets[m['id']] = m
                    
                    self.active_markets = new_markets
                    self.add_log(f"Discovered {len(self.active_markets)} active 5-min BTC markets.")
                else:
                    self.add_log(f"Gamma API error: {response.status_code}")
                
                await asyncio.sleep(60)
            except Exception as e:
                self.add_log(f"Market discovery error: {str(e)}")
                await asyncio.sleep(30)

    async def trading_loop(self):
        while True:
            if self.is_paused:
                await asyncio.sleep(2)
                continue
                
            try:
                for market_id, market in self.active_markets.items():
                    # Simplified edge calculation
                    title = market.get("title", "")
                    tokens = market.get("tokens", [])
                    if len(tokens) < 2:
                        continue
                        
                    yes_token = tokens[0]['token_id']
                    no_token = tokens[1]['token_id']
                    
                    try:
                        strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
                        strike = Decimal(strike_str)
                        
                        # Bayesian-ish edge (very simplified)
                        # Let's say we expect the probability of 'Yes' to be P
                        # If price is at strike, P = 0.5
                        # If price is 100 above strike, P -> 1.0
                        # We use a simple linear proxy for this MVP:
                        # P = 0.5 + (BTC_Price - Strike) / 200 (capped at 0.05 and 0.95)
                        
                        expected_prob = Decimal("0.5") + (self.btc_price - strike) / Decimal("200")
                        expected_prob = max(Decimal("0.05"), min(Decimal("0.95"), expected_prob))
                        
                        # In a real bot, we'd fetch the orderbook here:
                        # orderbook = self.clob_client.get_orderbook(yes_token)
                        # current_price = Decimal(str(orderbook.bids[0].price))
                        
                        # For simulation:
                        current_price_yes = expected_prob - Decimal("0.02") # Assume spread
                        
                        edge = expected_prob - current_price_yes
                        
                        if edge > self.edge_threshold:
                            side = "BUY"
                            self.add_log(f"Edge found! {edge*100:.1f}% on {title}. Placing {side} order.")
                            
                            if self.mode == "LIVE" and self.clob_client:
                                # Example order placement
                                # self.clob_client.create_order(OrderArgs(...))
                                pass
                            
                            self.stats["trades_last_hour"] += 1
                            self.stats["total_pnl"] += edge * Decimal("0.1") # Simulate small profit
                            
                    except Exception:
                        continue
                        
            except Exception as e:
                self.add_log(f"Trading loop error: {str(e)}")
                
            await asyncio.sleep(2)

    async def dashboard_refresh_loop(self, context: ContextTypes.DEFAULT_TYPE):
        while True:
            if self.dashboard_message_id and self.allowed_user_id:
                try:
                    text = self.get_dashboard_text()
                    keyboard = [
                        [InlineKeyboardButton("Refresh Stats", callback_data="refresh"),
                         InlineKeyboardButton("Toggle Pause", callback_data="toggle_pause")],
                        [InlineKeyboardButton("View Positions", callback_data="positions"),
                         InlineKeyboardButton("Recent Trades", callback_data="trades")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.edit_message_text(
                        chat_id=self.allowed_user_id,
                        message_id=self.dashboard_message_id,
                        text=text,
                        parse_mode="MarkdownV2",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    # Message might have been deleted or unchanged
                    pass
            await asyncio.sleep(15)

    def get_dashboard_text(self) -> str:
        status = "🟢 ACTIVE" if not self.is_paused else "🟡 PAUSED"
        mode = "🛑 LIVE" if self.mode == "LIVE" else "🧪 DRY-RUN"
        
        text = f"""
🤖 *Polymarket BTC Dashboard* \| {status}
🔥 *Mode:* {mode} \| 💰 *USDC:* `{self.stats['balance']}`
📈 *BTC Price:* `{self.btc_price}`

📊 *Performance (24h)*
├─ ⚡ *Trades:* `{self.stats['trades_last_hour']}`
├─ 🎯 *Win Rate:* `{self.stats['win_rate']}%`
├─ 📉 *Total P&L:* `{self.stats['total_pnl']}`
└─ 🧱 *Net Delta:* `{self.stats['net_delta']}`

📋 *Latest Activity*
```
{chr(10).join(self.stats['last_logs'])}
```
"""
        # Escape markdown special characters
        for char in ['-', '.', '!', '+', '(', ')']:
            text = text.replace(char, f"\\{char}")
        return text

    async def start_telegram(self):
        app = Application.builder().token(self.telegram_token).build()
        
        # Commands
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("pause", self.cmd_pause))
        app.add_handler(CommandHandler("resume", self.cmd_resume))
        app.add_handler(CommandHandler("setthreshold", self.cmd_set_threshold))
        
        # Callbacks
        app.add_handler(CallbackQueryHandler(self.handle_callbacks))
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        self.add_log("Telegram Bot started.")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.allowed_user_id:
            await update.message.reply_text("⛔ Unauthorized.")
            return
            
        text = self.get_dashboard_text()
        keyboard = [
            [InlineKeyboardButton("Refresh Stats", callback_data="refresh"),
             InlineKeyboardButton("Toggle Pause", callback_data="toggle_pause")],
            [InlineKeyboardButton("View Positions", callback_data="positions"),
             InlineKeyboardButton("Recent Trades", callback_data="trades")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(text, parse_mode="MarkdownV2", reply_markup=reply_markup)
        self.dashboard_message_id = msg.message_id
        
        # Start background dashboard refresh
        asyncio.create_task(self.dashboard_refresh_loop(context))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.cmd_start(update, context)

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = True
        self.add_log("Bot paused by user.")
        await update.message.reply_text("🟡 Bot PAUSED.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.is_paused = False
        self.add_log("Bot resumed by user.")
        await update.message.reply_text("🟢 Bot RESUMED.")

    async def cmd_set_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            new_val = Decimal(context.args[0])
            self.edge_threshold = new_val
            await update.message.reply_text(f"✅ Edge threshold set to: {new_val}")
        except:
            await update.message.reply_text("❌ Usage: /setthreshold <decimal>")

    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == "refresh":
            await query.edit_message_text(text=self.get_dashboard_text(), parse_mode="MarkdownV2", reply_markup=query.message.reply_markup)
        elif query.data == "toggle_pause":
            self.is_paused = not self.is_paused
            self.add_log(f"Bot {'PAUSED' if self.is_paused else 'RESUMED'} via dashboard.")
            await query.edit_message_text(text=self.get_dashboard_text(), parse_mode="MarkdownV2", reply_markup=query.message.reply_markup)

async def main():
    bot = TradingBot()
    await bot.init_polymarket()
    
    # Run tasks
    await asyncio.gather(
        bot.start_telegram(),
        bot.price_feed_loop(),
        bot.market_discovery_loop(),
        bot.trading_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")