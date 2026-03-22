"""
Points System Management for RecondTrade Bot
Tracks user points, Pro status, and leaderboard
Uses SQLite for persistent storage
"""
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from config import config

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """User information and points"""
    user_id: int
    username: str
    total_points: int
    balance_usdc: Decimal
    is_pro: bool
    pro_expiry: Optional[datetime]
    referral_code: str
    referred_by: Optional[int]
    trades_count: int
    trades_today: int
    pnl_total: Decimal
    pnl_today: Decimal
    first_seen: datetime
    last_active: datetime


class PointsManager:
    """Manage points, referrals, Pro status"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.POINTS_DB_PATH
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for points tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                total_points INTEGER DEFAULT 0,
                balance_usdc TEXT DEFAULT '0.0',
                is_pro BOOLEAN DEFAULT 0,
                pro_expiry TIMESTAMP,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                trades_count INTEGER DEFAULT 0,
                trades_today INTEGER DEFAULT 0,
                pnl_total TEXT DEFAULT '0.0',
                pnl_today TEXT DEFAULT '0.0',
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Points history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS points_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                points_delta INTEGER,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                market_id TEXT,
                edge Decimal,
                pnl TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.commit()
        conn.close()
        logger.info("✅ Points database initialized")

    def get_or_create_user(self, user_id: int, username: str) -> UserProfile:
        """Get or create user profile."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_profile(row)

        # Create new user
        import uuid
        referral_code = str(uuid.uuid4())[:8].upper()

        cursor.execute("""
            INSERT INTO users (user_id, username, referral_code)
            VALUES (?, ?, ?)
        """, (user_id, username, referral_code))

        conn.commit()

        # Award join bonus
        self.add_points(
            user_id,
            config.POINTS_PER_START,
            "Joined RecondTrade Bot"
        )

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        return self._row_to_profile(row)

    def add_points(self, user_id: int, points: int, reason: str = ""):
        """Add points to user account."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Update user points
        cursor.execute("""
            UPDATE users SET total_points = total_points + ?
            WHERE user_id = ?
        """, (points, user_id))

        # Record history
        cursor.execute("""
            INSERT INTO points_history (user_id, points_delta, reason)
            VALUES (?, ?, ?)
        """, (user_id, points, reason))

        conn.commit()
        conn.close()

        logger.info(f"➕ User {user_id}: +{points} points ({reason})")

    def get_top_users(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get top users by points."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT username, total_points FROM users
            ORDER BY total_points DESC
            LIMIT ?
        """, (limit,))

        results = cursor.fetchall()
        conn.close()

        return results

    def grant_pro(self, user_id: int, duration_days: int = 30) -> bool:
        """Grant Pro status for N days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        expiry = datetime.now(timezone.utc) + timedelta(days=duration_days)

        cursor.execute("""
            UPDATE users
            SET is_pro = 1, pro_expiry = ?
            WHERE user_id = ?
        """, (expiry.isoformat(), user_id))

        conn.commit()
        conn.close()

        logger.info(f"✅ Granted Pro status to user {user_id} until {expiry}")
        return True

    def revoke_pro(self, user_id: int) -> bool:
        """Revoke Pro status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET is_pro = 0, pro_expiry = NULL
            WHERE user_id = ?
        """, (user_id,))

        conn.commit()
        conn.close()

        return True

    def is_pro(self, user_id: int) -> bool:
        """Check if user has active Pro status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT is_pro, pro_expiry FROM users WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return False

        is_pro, pro_expiry = row
        if not is_pro:
            return False

        # Check if Pro status has expired
        if pro_expiry:
            expiry_dt = datetime.fromisoformat(pro_expiry)
            if datetime.now(timezone.utc) > expiry_dt:
                self.revoke_pro(user_id)
                return False

        return True

    def record_trade(self, user_id: int, market_id: str, edge: Decimal, pnl: Decimal = Decimal("0")):
        """Record a trade for points calculation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Update trade counters
        cursor.execute("""
            UPDATE users
            SET trades_count = trades_count + 1,
                trades_today = trades_today + 1,
                pnl_total = pnl_total + ?,
                pnl_today = pnl_today + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (str(pnl), str(pnl), user_id))

        # Record trade
        cursor.execute("""
            INSERT INTO trades (user_id, market_id, edge, pnl)
            VALUES (?, ?, ?, ?)
        """, (user_id, market_id, str(edge), str(pnl)))

        conn.commit()

        # Award points
        points = config.POINTS_PER_DETECTED_TRADE
        if edge > Decimal("0.05"):  # High edge bonus
            points += config.POINTS_PER_HIGH_EDGE

        # Pro multiplier
        if self.is_pro(user_id):
            points = int(points * config.PRO_MULTIPLIER)

        self.add_points(user_id, points, f"Trade detected (edge: {edge*100:.1f}%)")

        conn.close()

    def reset_daily_stats(self):
        """Reset daily trade counters (call once per day)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users SET trades_today = 0, pnl_today = '0.0'
        """)

        conn.commit()
        conn.close()

        logger.info("📊 Daily stats reset")

    def _row_to_profile(self, row) -> UserProfile:
        """Convert database row to UserProfile."""
        return UserProfile(
            user_id=row[0],
            username=row[1],
            total_points=row[2],
            balance_usdc=Decimal(row[3]),
            is_pro=bool(row[4]),
            pro_expiry=datetime.fromisoformat(row[5]) if row[5] else None,
            referral_code=row[6],
            referred_by=row[7],
            trades_count=row[8],
            trades_today=row[9],
            pnl_total=Decimal(row[10]),
            pnl_today=Decimal(row[11]),
            first_seen=datetime.fromisoformat(row[12]),
            last_active=datetime.fromisoformat(row[13]),
        )
