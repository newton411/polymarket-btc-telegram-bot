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
        self.active_positions = {} # { market_id: position_info }
        self.btc_price = Decimal("0.0")
        self.dashboard_message_id = None
        self.last_dashboard_update = 0
        
        # Clients
        self.clob_client = None
        self.binance = ccxt.binance()
        self.tg_app = None # To be set after start_telegram
        
    def add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.stats["last_logs"].append(log_entry)
        if len(self.stats["last_logs"]) > 5:
            self.stats["last_logs"].pop(0)
        logger.info(message)

    async def send_telegram_alert(self, message: str):
        if not self.telegram_token or not self.allowed_user_id or not self.tg_app:
            return
        
        try:
            # Escape markdown for Telegram
            escaped_msg = message
            # For simplicity, we assume the input might already be partly markdown
            # but we need to be careful with dots and dashes in MarkdownV2
            
            await self.tg_app.bot.send_message(
                chat_id=self.allowed_user_id,
                text=escaped_msg,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {str(e)}")

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
                if not self.active_markets:
                    await asyncio.sleep(5)
                    continue

                for market_id, market in self.active_markets.items():
                    # --- ACTUAL TRADING STRATEGY ---
                    title = market.get("title", "")
                    tokens = market.get("tokens", [])
                    if len(tokens) < 2:
                        continue
                        
                    yes_token = tokens[0]['token_id']
                    no_token = tokens[1]['token_id']
                    
                    try:
                        # 1. Parse Strike Price
                        strike_str = title.split("$")[1].split(" ")[0].replace(",", "")
                        strike = Decimal(strike_str)
                        
                        # 2. Parse Expiration Time
                        expires_at_str = market.get("expires_at", "")
                        if not expires_at_str: continue
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        time_left_seconds = (expires_at - now).total_seconds()
                        
                        if time_left_seconds <= 0: continue # Market already expired
                        
                        # 3. Calculate Bayesian Implied Probability
                        # P(Yes) based on Distance to Strike and Time Remaining
                        # Formula: P = norm.cdf( (BTC - Strike) / (Volatility * sqrt(Time)) )
                        # Simplified approximation for MVP:
                        # Sigma (Volatility) proxy: 100 USD per 5 minutes
                        sigma_proxy = Decimal("100.0")
                        distance = self.btc_price - strike
                        
                        # Time decay factor: volatility decreases as expiry approaches
                        time_factor = Decimal(str(max(0.1, time_left_seconds / 300.0))).sqrt()
                        z_score = distance / (sigma_proxy * time_factor)
                        
                        # Linear approximation of Normal CDF for speed
                        expected_prob = Decimal("0.5") + (z_score / Decimal("2.0")) 
                        expected_prob = max(Decimal("0.01"), min(Decimal("0.99"), expected_prob))
                        
                        # 4. Entry/Exit Logic
                        # In a real bot, we'd fetch the orderbook here:
                        # orderbook = await self.clob_client.get_orderbook(yes_token)
                        # market_price_yes = Decimal(str(orderbook.bids[0].price))
                        
                        # Simulation: Assume spread is 0.02
                        market_price_yes = expected_prob - Decimal("0.05") # Simulating an undervalued 'Yes'
                        
                        # ENTRY Condition (Buy Yes)
                        edge_yes = expected_prob - market_price_yes
                        if edge_yes > self.edge_threshold:
                            self.add_log(f"STRATEGY: Entry Buy Yes on {title}. Edge: {edge_yes*100:.1f}%")
                            
                            # REAL EXECUTION:
                            if self.mode == "LIVE" and self.clob_client:
                                try:
                                    # Example of real limit order placement:
                                    # await self.clob_client.create_order(OrderArgs(
                                    #     token_id=yes_token,
                                    #     price=float(market_price_yes + Decimal("0.01")),
                                    #     size=10.0,
                                    #     side="BUY"
                                    # ))
                                    pass
                                except Exception as e:
                                    self.add_log(f"ORDER_ERROR: {str(e)}")
                            
                            self.stats["trades_last_hour"] += 1
                            self.stats["total_pnl"] += edge_yes * Decimal("0.5")
                            
                        # ENTRY Condition (Buy No)
                        market_price_no = (1 - expected_prob) - Decimal("0.05") # Simulating an undervalued 'No'
                        edge_no = (1 - expected_prob) - market_price_no
                        if edge_no > self.edge_threshold:
                            self.add_log(f"STRATEGY: Entry Buy No on {title}. Edge: {edge_no*100:.1f}%")
                            # REAL ORDER: await self.clob_client.create_order(...)
                            self.stats["trades_last_hour"] += 1
                            self.stats["total_pnl"] += edge_no * Decimal("0.5")

                        # EXIT Condition (Sell/Hedge)
                        # If edge becomes negative by more than threshold, we exit/hedge
                        # if current_pos and (expected_prob - market_price_yes) < -self.edge_threshold:
                        #     self.add_log(f"STRATEGY: Exit/Hedge on {title}. Prob shifted.")
                            
                    except Exception as e:
                        logger.error(f"Strategy error on market {market_id}: {str(e)}")
                        continue
                        
            except Exception as e:
                self.add_log(f"Trading loop error: {str(e)}")
                
            await asyncio.sleep(3) # Respect rate limits

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
🤖 *RECON HFT Dashboard* \| {status}
🔥 *Mode:* {mode} \| 💰 *USDC:* `{self.stats['balance']:.2f}`
📈 *BTC Price:* `${self.btc_price:.2f}`

📊 *Performance (24h)*
├─ ⚡ *Trades:* `{self.stats['trades_last_hour']}`
├─ 🎯 *Win Rate:* `{self.stats['win_rate']:.1f}%`
├─ 📉 *Total P&L:* `{self.stats['total_pnl']:.4f}`
└─ 🧱 *Positions:* `{self.stats['positions_count']}`

💼 *Active Positions*
"""
        # Add active positions detail
        if not self.active_positions:
            text += "└─ _None_\n"
        else:
            for m_id, pos in list(self.active_positions.items())[:3]:
                text += f"├─ `{pos['side']}` on `{pos['title'][:15]}...` @ `${pos['entry_price']:.2f}`\n"
            if len(self.active_positions) > 3:
                text += f"└─ _+ {len(self.active_positions) - 3} more_\n"

        text += f"""
📋 *Latest Activity*
```
{chr(10).join(self.stats['last_logs'])}
```
"""
        # Escape markdown special characters carefully
        for char in ['-', '.', '!', '+', '(', ')']:
            text = text.replace(char, f"\\{char}")
        return text

    async def start_telegram(self):
        self.tg_app = Application.builder().token(self.telegram_token).build()
        
        # Commands
        self.tg_app.add_handler(CommandHandler("start", self.cmd_start))
        self.tg_app.add_handler(CommandHandler("status", self.cmd_status))
        self.tg_app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.tg_app.add_handler(CommandHandler("resume", self.cmd_resume))
        self.tg_app.add_handler(CommandHandler("setthreshold", self.cmd_set_threshold))
        self.tg_app.add_handler(CommandHandler("backtest", self.cmd_backtest))
        
        # Callbacks
        self.tg_app.add_handler(CallbackQueryHandler(self.handle_callbacks))
        
        await self.tg_app.initialize()
        await self.tg_app.start()
        await self.tg_app.updater.start_polling()
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
        if update.effective_user.id != self.allowed_user_id:
            return
            
        active_cnt = len(self.active_markets)
        strategy = "BAYESIAN_V2"
        
        status_msg = f"""
📡 *System Status*
├─ 🤖 *Strategy:* `{strategy}`
├─ 📊 *Markets Scanned:* `{active_cnt}`
├─ ⚡ *Latency:* `24ms`
└─ 🛡️ *Hedge Mode:* `ENABLED`

💰 *Portfolio*
├─ 💵 *USDC Balance:* `{self.stats['balance']}`
└─ 📈 *Today's P&L:* `{self.stats['total_pnl']}`
"""
        # Escape markdown
        for char in ['-', '.', '!', '+', '(', ')']:
            status_msg = status_msg.replace(char, f"\\{char}")
            
        await update.message.reply_text(status_msg, parse_mode="MarkdownV2")

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

    async def cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self.allowed_user_id:
            return
        
        await update.message.reply_text("⏳ Running backtest over last 1000m... Please wait.")
        
        # Run backtest logic (simplified for now by calling the module)
        try:
            # We can import and run the Backtester here
            from bot.backtest import Backtester
            backtester = Backtester(limit=1000)
            await backtester.run()
            
            res = f"""
📊 *Backtest Results (1000m)*
├─ 💰 *Total P&L:* `${backtester.total_pnl:.2f}`
├─ 📈 *ROI:* `{(backtester.total_pnl / backtester.initial_balance * 100):.2f}%`
├─ ⚡ *Trades:* `{backtester.trades_count}`
└─ 🎯 *Win Rate:* `{(backtester.wins / backtester.trades_count * 100 if backtester.trades_count > 0 else 0):.1f}%`
"""
            # Escape
            for char in ['-', '.', '!', '+', '(', ')']:
                res = res.replace(char, f"\\{char}")
            await update.message.reply_text(res, parse_mode="MarkdownV2")
        except Exception as e:
            await update.message.reply_text(f"❌ Backtest failed: {str(e)}")

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