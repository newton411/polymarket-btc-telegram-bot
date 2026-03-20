"""
Telegram bot handlers and dashboard for Polymarket trading bot
"""
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

from config import config

logger = logging.getLogger(__name__)

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