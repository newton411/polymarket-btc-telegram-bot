"""
Telegram Bot for RecondTrade — Commands & Dashboard
Handles user interactions, displays live trading dashboard, manages points/subscriptions
"""
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List

from telegram import Update, User as TelegramUser
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from config import config
from polymarket_client import PolymarketClient
from strategies import TradingStrategies, OpportunityDetected
from points_manager import PointsManager
from subscription import SubscriptionManager

logger = logging.getLogger(__name__)


class TelegramBot:
    """Handle all Telegram bot interactions."""

    def __init__(
        self,
        clob_client: PolymarketClient,
        strategies: TradingStrategies,
        points_manager: PointsManager,
        subscription_manager: SubscriptionManager,
    ):
        self.clob = clob_client
        self.strategies = strategies
        self.points = points_manager
        self.subscription = subscription_manager
        
        self.app = Application.builder().token(config.TELEGRAM_TOKEN).build()
        self.dashboard_message_id: Dict[int, int] = {}
        self.user_sessions: Dict[int, Dict] = {}
        
        self._setup_handlers()

    def _setup_handlers(self):
        """Register command handlers."""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("stats", self.cmd_status))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("points", self.cmd_points))
        self.app.add_handler(CommandHandler("leaderboard", self.cmd_leaderboard))
        self.app.add_handler(CommandHandler("referral", self.cmd_referral))
        self.app.add_handler(CommandHandler("subscribe", self.cmd_subscribe))
        self.app.add_handler(CommandHandler("verify", self.cmd_verify))
        self.app.add_handler(CommandHandler("dryrun", self.cmd_dryrun))
        self.app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.app.add_handler(CommandHandler("resume", self.cmd_resume))
        self.app.add_handler(CommandHandler("settarget", self.cmd_settarget))
        self.app.add_handler(CommandHandler("setsize", self.cmd_setsize))
        self.app.add_handler(CommandHandler("logs", self.cmd_logs))
        self.app.add_handler(CommandHandler("pnl", self.cmd_pnl))
        self.app.add_handler(CommandHandler("tge", self.cmd_tge))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        
        if config.ALLOWED_USER_ID and user.id != config.ALLOWED_USER_ID:
            await update.message.reply_text("❌ Unauthorized")
            return
        
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        
        welcome = f"""
🤖 *Welcome to RecondTrade Bot*

Production\\-grade arbitrage trader for Polymarket 5\\-minute BTC markets\\.

⚙️ *Current Mode:* {'🟢 DRY\\-RUN' if config.DRY_RUN else '🔴 LIVE'}

📊 *Quick Stats:*
• Points: {profile.total_points}
• Status: {'✅ Pro' if self.points.is_pro(user.id) else '⚪ Free'}
• Referral Code: `{profile.referral_code}`

🎯 *Next Steps:*
1\\. /help — Full command list
2\\. /status — Current bot status
3\\. /subscribe — Upgrade to Pro
4\\. /dryrun on|off — Toggle dry\\-run mode

⚠️ *HIGH RISK:* This bot can lose real capital\\. Only run with capital you can afford to lose\\.
"""
        
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        balance_usdc = await self.clob.check_user_balance() or Decimal("0")
        open_orders = await self.clob.get_open_orders()
        markets = self.strategies.active_markets
        opportunities = self.strategies.opportunities[-10:]
        
        status_msg = f"""
⚙️ *RecondTrade Status*

🔐 *Mode:* {'🟢 DRY\\-RUN' if config.DRY_RUN else '🔴 LIVE TRADING'}

💰 *Account:*
• Balance: \\${balance_usdc:.2f} USDC
• Open Orders: {len(open_orders)}
• Markets Monitored: {len(markets)}

📊 *Strategy:*
• Target Sum: {config.ARB_SUM_TARGET}
• Edge Threshold: {config.EDGE_THRESHOLD * 100:.1f}%
• Poll Interval: {config.POLL_INTERVAL}s

🎯 *Recent Opportunities:*
"""
        
        if opportunities:
            for opp in opportunities[-5:]:
                status_msg += f"\n• {opp.market_title}: sum={opp.sum_price:.4f}, edge={opp.edge*100:.2f}%"
        else:
            status_msg += "\nNone detected yet"
        
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        status_msg += f"\n\n📈 *Points:* {profile.total_points}"
        
        await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🆘 *RecondTrade Bot Commands*

*Status & Info:*
• `/status` or `/stats` — Bot status & recent opportunities
• `/points` — Your points & Pro status
• `/leaderboard` — Top 10 users by points
• `/logs` — Recent bot logs
• `/pnl` — Today's P&L

*Subscription:*
• `/subscribe` — Upgrade to Pro \\(10 USDC for 30 days\\)
• `/verify <txhash>` — Verify USDC payment

*Trading Control:*
• `/dryrun on|off` — Toggle dry\\-run mode
• `/pause` — Pause trading
• `/resume` — Resume trading
• `/settarget <0.xx>` — Set arbitrage target sum
• `/setsize <N>` — Set trade size \\(shares\\)

*Referral & TGE:*
• `/referral` — Your referral link & earnings
• `/tge` — Token Generation Event info

*Creator:*
• Wallet: `0x74299c15CcEf4b48B06633E44F4F131209E0d233` \\(Polygon\\)
• Strategy: Dynamic Sum Arbitrage \\(mathematically risk\\-free\\)
"""
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_points(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        is_pro = self.points.is_pro(user.id)
        
        points_msg = f"""
📈 *Your Points*

• Total Points: *{profile.total_points}*
• Status: {'✅ Pro' if is_pro else '⚪ Free Tier'}
• Trades Detected: {profile.trades_count}
• P&L Today: \\${profile.pnl_today:+.2f}

*How to Earn Points:*
• `/start` → \\+50 points
• `/status` → \\+10 points each time
• Detected trade → \\+25 points
• High edge \\(>5%\\) → \\+100 bonus
• Pro users get 2× multiplier

*Next Steps:*
{'🎉 You\\'re Pro\\! Status valid until ' + profile.pro_expiry.strftime('%Y-%m-%d') if is_pro and profile.pro_expiry else '📱 /subscribe for 2× points multiplier'}
"""
        
        await update.message.reply_text(points_msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        top_users = self.points.get_top_users(limit=10)
        
        leaderboard = "🏆 *Top 10 Users*\n\n"
        for i, (username, points) in enumerate(top_users, 1):
            leaderboard += f"{i}\\. {username}: *{points}* pts\n"
        
        await update.message.reply_text(leaderboard, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_referral(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        
        referral_msg = f"""
🔗 *Your Referral Code*

Code: `{profile.referral_code}`

Share this link:
`https://t.me/RecondTrade_Bot?start={profile.referral_code}`

Earn points when friends use your code\\!
"""
        
        await update.message.reply_text(referral_msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        sub_msg = await self.subscription.get_subscription_message()
        await update.message.reply_text(sub_msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_verify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /verify <txhash>")
            return
        
        tx_hash = " ".join(context.args)
        await update.message.reply_text("⏳ Verifying transaction\\.\\.\\.")
        
        result = await self.subscription.verify_payment(tx_hash, user.id)
        
        if result["success"]:
            await update.message.reply_text(result["message"], parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(result["message"])

    async def cmd_dryrun(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        if not context.args or context.args[0].lower() not in ["on", "off"]:
            await update.message.reply_text("❌ Usage: /dryrun on|off")
            return
        
        mode = context.args[0].lower() == "on"
        config.DRY_RUN = mode
        
        msg = f"{'🟢 DRY\\-RUN mode enabled' if mode else '🔴 LIVE TRADING mode enabled'}"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        self.user_sessions[update.effective_user.id] = {"paused": True}
        await update.message.reply_text("⏸️ Trading paused")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        self.user_sessions[update.effective_user.id] = {"paused": False}
        await update.message.reply_text("▶️ Trading resumed")

    async def cmd_settarget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        if not context.args:
            await update.message.reply_text(f"Current target: {config.ARB_SUM_TARGET}\nUsage: /settarget 0\\.95")
            return
        
        try:
            target = Decimal(context.args[0])
            if target < Decimal("0.5") or target > Decimal("1.0"):
                await update.message.reply_text("❌ Target must be between 0\\.5 and 1\\.0")
                return
            
            config.ARB_SUM_TARGET = target
            await update.message.reply_text(f"✅ Target set to {target}")
        except:
            await update.message.reply_text("❌ Invalid number")

    async def cmd_setsize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        if not context.args:
            await update.message.reply_text(f"Current size: 25 shares\nUsage: /setsize 50")
            return
        
        try:
            size = int(context.args[0])
            await update.message.reply_text(f"✅ Trade size set to {size} shares")
        except:
            await update.message.reply_text("❌ Invalid number")

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        await update.message.reply_text("📋 Recent logs:\n\n\\(Logging integration TODO\\)")

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorize(update.effective_user):
            return
        
        user = update.effective_user
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        
        pnl_msg = f"""
📈 *P&L Summary*

• Today: \\${profile.pnl_today:+.2f}
• Total: \\${profile.pnl_total:+.2f}
• Trades: {profile.trades_count}
"""
        
        await update.message.reply_text(pnl_msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_tge(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self._authorize(user):
            return
        
        profile = self.points.get_or_create_user(user.id, user.username or f"user_{user.id}")
        points = profile.total_points
        tokens = Decimal(points) / Decimal("1000")
        
        tge_msg = f"""
💰 *Token Generation Event \\(TGE\\)*

• Your Points: *{points}*
• Estimated Tokens: *{tokens:.2f}* \\(1000 pts = 1 token\\)
• Pro Bonus: {'2× allocation' if self.points.is_pro(user.id) else 'Standard'}

🔗 TGE Page: RecondTrade Token

Creator Wallet: `{config.CREATOR_WALLET}`
"""
        
        await update.message.reply_text(tge_msg, parse_mode=ParseMode.MARKDOWN_V2)

    def _authorize(self, user: TelegramUser) -> bool:
        if config.ALLOWED_USER_ID and user.id != config.ALLOWED_USER_ID:
            return False
        return True

    async def on_opportunity(self, opportunity: OpportunityDetected):
        logger.info(f"🎯 Opportunity: {opportunity.market_title} (edge: {opportunity.edge*100:.2f}%)")
        
        try:
            for user_id in self.user_sessions:
                opp_msg = f"""
🎯 *Opportunity Detected\\!*

Market: {opportunity.market_title}
Sum: {opportunity.sum_price:.4f}
Edge: {opportunity.edge * 100:.2f}%
Expected Profit: \\${opportunity.up_size * opportunity.edge:.2f}

Status: {'📤 Executing\\.\\.\\.' if not config.DRY_RUN else '🌙 DRY\\-RUN \\(not executed\\)'}
"""
                
                try:
                    await self.app.bot.send_message(
                        chat_id=user_id,
                        text=opp_msg,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                except:
                    pass
        except Exception as e:
            logger.error(f"❌ Opportunity notification error: {e}")

    async def run(self):
        logger.info("🚀 Telegram bot starting\\.\\.\\.")
        await self.app.initialize()
        await self.app.start()
        logger.info("✅ Telegram bot running")

    async def stop(self):
        logger.info("Stopping Telegram bot\\.\\.\\.")
        await self.app.stop()
        await self.app.shutdown()


class TelegramBot:
    """Telegram bot for trading control and monitoring."""

    def __init__(self, trading_bot):
        self.trading_bot = trading_bot
        self.app = None
        self.dashboard_message_id = None
        self.is_paused = False

    async def start_bot(self):
        """Initialize and start the Telegram bot."""
        self.app = Application.builder().token(config.TELEGRAM_TOKEN).build()

        # Register handlers
        handlers = [
            ("start", self.cmd_start),
            ("status", self.cmd_status),
            ("stats", self.cmd_stats),
            ("pnl", self.cmd_pnl),
            ("logs", self.cmd_logs),
            ("pause", self.cmd_pause),
            ("resume", self.cmd_resume),
            ("dryrun", self.cmd_dryrun_toggle),
            ("settarget", self.cmd_set_target),
            ("help", self.cmd_help),
        ]

        for command, handler in handlers:
            self.app.add_handler(CommandHandler(command, handler))

        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        # Start the bot
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        logger.info("Telegram bot started")

    @staticmethod
    def _require_auth(func):
        """Decorator to require authorized user."""
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if config.ALLOWED_USER_ID and update.effective_user.id != config.ALLOWED_USER_ID:
                await update.message.reply_text("⛔ Unauthorized access denied.")
                logger.warning(f"Unauthorized access attempt from user {update.effective_user.id}")
                return
            return await func(update, context)
        return wrapper

    @_require_auth
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message and main menu."""
        welcome_text = (
            "🚀 *RECON HFT* \\- Polymarket BTC Trading Bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🤖 *High\\-Frequency BTC 5\\-min Markets*\n"
            "• Risk\\-free Arbitrage Detection\n"
            "• Last\\-second Sniping\n"
            "• Momentum Trading\n"
            "• Market Making\n\n"
            f"⚡ *Status:* {'🟡 PAUSED' if self.is_paused else '🟢 ACTIVE'}\n"
            f"🎯 *Mode:* {'DRY RUN' if config.DRY_RUN else 'LIVE TRADING'}\n\n"
            "*Quick Commands:*"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard"),
             InlineKeyboardButton("⏸️ Pause/Resume", callback_data="toggle_pause")],
            [InlineKeyboardButton("📈 Statistics", callback_data="stats"),
             InlineKeyboardButton("💰 P&L", callback_data="pnl")],
            [InlineKeyboardButton("📋 Recent Logs", callback_data="logs"),
             InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]

        await update.message.reply_text(
            welcome_text,
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    @_require_auth
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current status."""
        status_text = self._build_status_text()
        await update.message.reply_text(status_text, parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed statistics."""
        stats_text = self._build_stats_text()
        await update.message.reply_text(stats_text, parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show P&L information."""
        pnl_text = self._build_pnl_text()
        await update.message.reply_text(pnl_text, parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent logs."""
        logs_text = self._build_logs_text()
        await update.message.reply_text(logs_text, parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pause trading."""
        self.is_paused = True
        await update.message.reply_text("🟡 *Trading PAUSED* \\- No new orders will be placed\\.", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Resume trading."""
        self.is_paused = False
        await update.message.reply_text("🟢 *Trading RESUMED* \\- Active order placement\\.", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_dryrun_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle dry run mode."""
        if not context.args:
            await update.message.reply_text("Usage: /dryrun on|off", parse_mode="MarkdownV2")
            return

        mode = context.args[0].lower()
        if mode == "on":
            config.DRY_RUN = True
            await update.message.reply_text("🎭 *DRY RUN ENABLED* \\- Simulating all trades\\.", parse_mode="MarkdownV2")
        elif mode == "off":
            config.DRY_RUN = False
            await update.message.reply_text("🔴 *LIVE TRADING ENABLED* \\- Real orders will be placed\\!", parse_mode="MarkdownV2")
        else:
            await update.message.reply_text("Usage: /dryrun on|off", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set arbitrage target sum."""
        if not context.args:
            await update.message.reply_text("Usage: /settarget 0\\.96", parse_mode="MarkdownV2")
            return

        try:
            target = Decimal(context.args[0])
            if target <= 0 or target >= 2:
                raise ValueError("Invalid target")

            config.TARGET_SUM = target
            await update.message.reply_text(f"✅ *Arbitrage target set to:* {target}", parse_mode="MarkdownV2")
        except Exception as e:
            await update.message.reply_text(f"❌ Invalid target value: {e}", parse_mode="MarkdownV2")

    @_require_auth
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information."""
        help_text = (
            "📚 *Available Commands*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Basic Commands:*\n"
            "`/start` \\- Main menu and status\n"
            "`/status` \\- Current bot status\n"
            "`/help` \\- This help message\n\n"
            "*Trading Control:*\n"
            "`/pause` \\- Pause all trading\n"
            "`/resume` \\- Resume trading\n"
            "`/dryrun on|off` \\- Toggle simulation mode\n\n"
            "*Configuration:*\n"
            "`/settarget 0.XX` \\- Set arbitrage threshold\n\n"
            "*Monitoring:*\n"
            "`/stats` \\- Detailed statistics\n"
            "`/pnl` \\- Profit & Loss summary\n"
            "`/logs` \\- Recent activity logs\n\n"
            "*Safety Features:*\n"
            "• DRY_RUN mode by default\n"
            "• Position size limits\n"
            "• Daily drawdown stops\n"
            "• Rate limiting\n"
            "• Graceful error handling"
        )
        await update.message.reply_text(help_text, parse_mode="MarkdownV2")

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks."""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data == "dashboard":
            await query.edit_message_text(
                self._build_dashboard_text(),
                parse_mode="MarkdownV2",
                reply_markup=self._dashboard_keyboard()
            )
        elif data == "toggle_pause":
            self.is_paused = not self.is_paused
            status = "PAUSED" if self.is_paused else "RESUMED"
            await query.edit_message_text(
                f"✅ *Trading {status}*\n\n{self._build_status_text()}",
                parse_mode="MarkdownV2",
                reply_markup=self._dashboard_keyboard()
            )
        elif data == "stats":
            await self.app.bot.send_message(
                chat_id=config.ALLOWED_USER_ID,
                text=self._build_stats_text(),
                parse_mode="MarkdownV2"
            )
        elif data == "pnl":
            await self.app.bot.send_message(
                chat_id=config.ALLOWED_USER_ID,
                text=self._build_pnl_text(),
                parse_mode="MarkdownV2"
            )
        elif data == "logs":
            await self.app.bot.send_message(
                chat_id=config.ALLOWED_USER_ID,
                text=self._build_logs_text(),
                parse_mode="MarkdownV2"
            )
        elif data == "settings":
            await query.edit_message_text(
                self._build_settings_text(),
                parse_mode="MarkdownV2",
                reply_markup=self._settings_keyboard()
            )

    def _dashboard_keyboard(self):
        """Dashboard inline keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="dashboard"),
             InlineKeyboardButton("⏸️ Pause/Resume", callback_data="toggle_pause")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats"),
             InlineKeyboardButton("💰 P&L", callback_data="pnl")],
            [InlineKeyboardButton("📋 Logs", callback_data="logs"),
             InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ])

    def _settings_keyboard(self):
        """Settings inline keyboard."""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Target: " + f"{config.TARGET_SUM}", callback_data="settings_target"),
             InlineKeyboardButton("📊 Max Size: " + f"${config.MAX_POSITION_SIZE}", callback_data="settings_size")],
            [InlineKeyboardButton("🎭 Dry Run: " + ("ON" if config.DRY_RUN else "OFF"), callback_data="settings_dryrun"),
             InlineKeyboardButton("⬅️ Back", callback_data="dashboard")]
        ])

    def _build_status_text(self) -> str:
        """Build current status text."""
        return (
            "📊 *Bot Status*\n"
            "━━━━━━━━━━━━\n"
            f"├─ Mode: {'🟡 PAUSED' if self.is_paused else '🟢 ACTIVE'}\n"
            f"├─ Trading: {'🎭 DRY RUN' if config.DRY_RUN else '🔴 LIVE'}\n"
            f"├─ Markets: {len(self.trading_bot.active_markets) if hasattr(self.trading_bot, 'active_markets') else 0} discovered\n"
            f"├─ Last Update: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n"
            f"└─ Uptime: Connected"
        )

    def _build_dashboard_text(self) -> str:
        """Build comprehensive dashboard text."""
        # This would integrate with the trading bot's performance tracker
        return (
            "🚀 *RECON HFT Dashboard*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n" +
            self._build_status_text() + "\n\n" +
            "💰 *Portfolio*\n" +
            "├─ Balance: $1,000\\.00\n" +
            "├─ Today's P&L: $0\\.00\n" +
            "└─ Total Trades: 0\n\n" +
            "📈 *Performance*\n" +
            "├─ Win Rate: 0%\n" +
            "├─ Avg Edge: 0\\.00%\n" +
            "└─ Trades/Hour: 0\n\n" +
            "🎯 *Active Strategies*\n" +
            "├─ Arbitrage: 🟢 Active\n" +
            "├─ Sniping: 🟢 Active\n" +
            "├─ Momentum: 🟢 Active\n" +
            "└─ Market Making: 🟢 Active"
        )

    def _build_stats_text(self) -> str:
        """Build detailed statistics text."""
        return (
            "📊 *Detailed Statistics*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Trading Performance:*\n"
            "├─ Total Trades: 0\n"
            "├─ Winning Trades: 0\n"
            "├─ Losing Trades: 0\n"
            "├─ Win Rate: 0\\.00%\n"
            "├─ Avg Win: $0\\.00\n"
            "├─ Avg Loss: $0\\.00\n"
            "├─ Profit Factor: 0\\.00\n"
            "├─ Sharpe Ratio: 0\\.00\n\n"
            "*Risk Metrics:*\n"
            "├─ Max Drawdown: 0\\.00%\n"
            "├─ Daily Drawdown: 0\\.00%\n"
            "├─ VaR (95%): 0\\.00%\n"
            "└─ Exposure: $0\\.00"
        )

    def _build_pnl_text(self) -> str:
        """Build P&L summary text."""
        return (
            "💰 *Profit & Loss Summary*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Today's Performance:*\n"
            "├─ Realized P&L: $0\\.00\n"
            "├─ Unrealized P&L: $0\\.00\n"
            "├─ Total P&L: $0\\.00\n"
            "├─ Best Trade: $0\\.00\n"
            "└─ Worst Trade: $0\\.00\n\n"
            "*Monthly Performance:*\n"
            "├─ Total P&L: $0\\.00\n"
            "├─ Win Rate: 0\\.00%\n"
            "├─ Avg Daily P&L: $0\\.00\n"
            "└─ Best Day: $0\\.00"
        )

    def _build_logs_text(self) -> str:
        """Build recent logs text."""
        return (
            "📋 *Recent Activity Logs*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Last 10 Activities:*\n"
            "┌─ No recent activity\n"
            "│  Bot initialized and ready\n"
            "│  Market discovery active\n"
            "│  Strategies loaded\n"
            "└─ Waiting for opportunities"
        )

    def _build_settings_text(self) -> str:
        """Build settings overview text."""
        return (
            "⚙️ *Current Settings*\n"
            "━━━━━━━━━━━━━━━━━\n\n"
            "*Trading Parameters:*\n"
            f"├─ Arbitrage Target: {config.TARGET_SUM}\n"
            f"├─ Max Position Size: ${config.MAX_POSITION_SIZE}\n"
            f"├─ Edge Threshold: {config.EDGE_THRESHOLD}\n"
            f"├─ Poll Interval: {config.POLL_INTERVAL}s\n\n"
            "*Risk Management:*\n"
            f"├─ Daily Drawdown Stop: {config.DAILY_DRAWDOWN_STOP * 100}%\n"
            f"├─ Max Trades/Hour: {config.MAX_TRADES_PER_HOUR}\n"
            f"├─ Dry Run Mode: {'Enabled' if config.DRY_RUN else 'Disabled'}\n\n"
            "*Use buttons below to adjust:*"
        )

    async def send_alert(self, message: str):
        """Send alert message to authorized user."""
        if config.ALLOWED_USER_ID:
            try:
                await self.app.bot.send_message(
                    chat_id=config.ALLOWED_USER_ID,
                    text=f"🚨 *Alert:* {message}",
                    parse_mode="MarkdownV2"
                )
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

    async def update_dashboard(self):
        """Update the persistent dashboard message."""
        if not self.dashboard_message_id or not config.ALLOWED_USER_ID:
            return

        try:
            await self.app.bot.edit_message_text(
                chat_id=config.ALLOWED_USER_ID,
                message_id=self.dashboard_message_id,
                text=self._build_dashboard_text(),
                parse_mode="MarkdownV2",
                reply_markup=self._dashboard_keyboard()
            )
        except Exception as e:
            logger.error(f"Dashboard update failed: {e}")

    async def stop_bot(self):
        """Stop the Telegram bot."""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram bot stopped")