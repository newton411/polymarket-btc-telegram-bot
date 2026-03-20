# Polymarket BTC HFT Bot 🤖

A high-frequency trading bot for Polymarket 5-minute Bitcoin markets with a Telegram dashboard.

## Features
- **HFT Trading Engine**: Targets 5-minute BTC markets using limit orders.
- **Simplified Bayesian Edge**: Models the probability of resolution based on BTC spot price (Binance).
- **Telegram Live Dashboard**: Monitor stats, P&L, and control the bot from Telegram.
- **Dry Run Mode**: Test strategies without risking capital.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration**:
   Copy `.env.example` to `.env` and fill in your credentials:
   - `POLYMARKET_PK`: Your Polygon private key.
   - `TELEGRAM_BOT_TOKEN`: Get from @BotFather.
   - `TELEGRAM_ALLOWED_USER_ID`: Get from @userinfobot.

3. **Run the Bot**:
   ```bash
   python main.py
   ```

## Trading Logic
The bot calculates the "implied probability" of a "Yes" outcome for 5-minute Bitcoin markets. It compares the current spot price from Binance with the market's strike price. 
- **Edge**: `Expected Probability - Market Price`.
- **Action**: Places limit orders when the edge exceeds the threshold (e.g., 10%).

## Risk Warning ⚠️
**THIS IS HIGH-RISK SOFTWARE.** Trading prediction markets involves significant risk of loss. Start in `DRY_RUN` mode and never trade with money you cannot afford to lose.

## Next Steps
- Implement real orderbook fetching using `clob_client.get_orderbook`.
- Add WebSocket support for real-time orderbook updates.
- Refine the Bayesian model with historical volatility data.
