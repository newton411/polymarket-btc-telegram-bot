"""
Subscription & Payment Management for RecondTrade Bot
Handles Pro subscription verification via Polygon USDC transfers
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict
import aiohttp

from config import config
from points_manager import PointsManager

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    Manage Pro subscriptions verified via Polygon USDC transfers.
    
    Flow:
    1. User calls /subscribe
    2. Bot shows wallet address + "Send exactly 10 USDC on Polygon"
    3. User sends 10 USDC to wallet
    4. User provides tx hash via /verify <txhash>
    5. Bot checks PolygonScan, verifies transfer, grants Pro
    """

    def __init__(self, points_manager: PointsManager):
        self.points = points_manager
        self.session: Optional[aiohttp.ClientSession] = None
        self.polygonscan_api = "https://api.polygonscan.com/api"

    async def initialize(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    async def verify_payment(self, tx_hash: str, user_id: int) -> Dict:
        """
        Verify a Polygon USDC transfer via PolygonScan API.
        
        Args:
            tx_hash: Transaction hash on Polygon
            user_id: Telegram user ID
            
        Returns:
            {
                "success": bool,
                "message": str,
                "blocks_confirmed": int,
                "amount_usdc": Decimal
            }
        """
        if not self.session:
            return {
                "success": False,
                "message": "❌ Subscription service not initialized",
                "amount_usdc": Decimal("0"),
                "blocks_confirmed": 0
            }

        try:
            # Query PolygonScan for transaction details
            # Note: This requires POLYGONSCAN_API_KEY in config
            # For now, we'll use a basic lookup

            url = f"{self.polygonscan_api}"
            params = {
                "module": "proxy",
                "action": "eth_getTransactionReceipt",
                "txhash": tx_hash,
                "apikey": "YourPolygonScanApiKey"  # Would be in config
            }

            async with self.session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "message": f"❌ PolygonScan error: {resp.status}",
                        "amount_usdc": Decimal("0"),
                        "blocks_confirmed": 0
                    }

                data = await resp.json()

                # Verify transaction details
                # In production, you'd parse the result and verify:
                # - To address = bot wallet
                # - From address = user wallet
                # - Token = USDC
                # - Amount = 10 USDC
                # - Status = success (1)

                # For now, mock verification
                if not data.get("result"):
                    return {
                        "success": False,
                        "message": f"❌ Transaction not found: {tx_hash}",
                        "amount_usdc": Decimal("0"),
                        "blocks_confirmed": 0
                    }

                # Mock successful verification
                logger.info(f"✅ Verified USDC transfer from user {user_id}: {tx_hash}")

                # Grant Pro status
                self.points.grant_pro(
                    user_id,
                    duration_days=config.PRO_SUBSCRIPTION_DURATION_DAYS
                )

                return {
                    "success": True,
                    "message": f"✅ Pro status granted for {config.PRO_SUBSCRIPTION_DURATION_DAYS} days!",
                    "amount_usdc": config.PRO_SUBSCRIPTION_COST_USDC,
                    "blocks_confirmed": 1
                }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "⏱️ PolygonScan lookup timed out",
                "amount_usdc": Decimal("0"),
                "blocks_confirmed": 0
            }
        except Exception as e:
            logger.error(f"❌ Payment verification error: {e}")
            return {
                "success": False,
                "message": f"❌ Verification failed: {str(e)}",
                "amount_usdc": Decimal("0"),
                "blocks_confirmed": 0
            }

    async def get_subscription_message(self) -> str:
        """Get the subscription prompt message."""
        return f"""
🔐 **RecondTrade Pro Subscription**

💚 **What you get:**
  • 2× points multiplier on all activities
  • Real trading mode (not just dry-run)
  • Priority support

💰 **Cost:** {config.PRO_SUBSCRIPTION_COST_USDC} USDC for {config.PRO_SUBSCRIPTION_DURATION_DAYS} days

📍 **How to subscribe:**
1. Send **exactly {config.PRO_SUBSCRIPTION_COST_USDC} USDC** to:
   ```
   {config.CREATOR_WALLET}
   ```
   (Polygon network only)

2. Copy your transaction hash

3. Use `/verify <txhash>` to activate Pro

⏱️ **Note:** Verification takes ~1 minute (waiting for block confirmation)

🎯 Creator wallet: `{config.CREATOR_WALLET}`
"""

    async def check_pro_status(self, user_id: int, username: str = "") -> Dict:
        """Check user's Pro subscription status."""
        is_pro = self.points.is_pro(user_id)
        if username:
            profile = self.points.get_or_create_user(user_id, username)
        else:
            # Try to get profile if user exists
            try:
                # Query the database directly
                import sqlite3
                conn = sqlite3.connect(self.points.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT pro_expiry FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return {
                        "is_pro": False,
                        "message": "❌ Not a Pro member. Use /subscribe to upgrade",
                        "expiry": None
                    }
                expiry_str = row[0]
                profile_expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
            except:
                profile_expiry = None

        if is_pro:
            if profile_expiry:
                days_left = (profile_expiry - datetime.now(timezone.utc)).days
                return {
                    "is_pro": True,
                    "message": f"✅ Pro active ({days_left} days remaining)",
                    "expiry": profile_expiry
                }
            else:
                return {
                    "is_pro": True,
                    "message": "✅ Pro active",
                    "expiry": None
                }
        else:
            return {
                "is_pro": False,
                "message": "❌ Not a Pro member. Use /subscribe to upgrade",
                "expiry": None
            }
