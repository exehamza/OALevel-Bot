import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

# Adjust parents index so PROJECT_ROOT points to your top-level bot directory:
# Use .parents[1] if this script is in `cogs/`
PROJECT_ROOT = Path(__file__).resolve().parents[1] 

# Point the default database directly into the persistent `data/` directory
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "economy.db"

DB_PATH = os.environ.get("ECONOMY_DB_PATH", str(DEFAULT_DB_PATH))
LEGACY_DATA_DB_PATH = DEFAULT_DB_PATH


class EconomyDB:
    @staticmethod
    async def init_db():
        """Create and migrate the economy database schema."""
        db_parent = Path(DB_PATH).expanduser().parent
        if str(db_parent) not in ("", "."):
            db_parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._ensure_core_tables(db)
            await EconomyDB._ensure_passive_tables(db)
            await EconomyDB._ensure_inventory_tables(db)
            await EconomyDB._maybe_migrate_legacy_data_db(db)
            await db.commit()

    @staticmethod
    async def init_passive_db():
        """Create passive rig tracking tables."""
        db_parent = Path(DB_PATH).expanduser().parent
        if str(db_parent) not in ("", "."):
            db_parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._ensure_passive_tables(db)
            await db.commit()

    @staticmethod
    async def _ensure_core_tables(db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy_users (
                user_id INTEGER PRIMARY KEY,
                nodes INTEGER DEFAULT 0,
                bank_nodes INTEGER DEFAULT 0,
                last_daily REAL DEFAULT 0,
                last_monthly REAL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                amount INTEGER,
                details TEXT,
                timestamp REAL
            )
        """)

        user_cols = await EconomyDB._table_columns(db, "economy_users")
        if "nodes" not in user_cols:
            await db.execute("ALTER TABLE economy_users ADD COLUMN nodes INTEGER DEFAULT 0")
        if "bank_nodes" not in user_cols:
            await db.execute("ALTER TABLE economy_users ADD COLUMN bank_nodes INTEGER DEFAULT 0")
            user_cols.add("bank_nodes")
        if "last_daily" not in user_cols:
            await db.execute("ALTER TABLE economy_users ADD COLUMN last_daily REAL DEFAULT 0")
        if "last_monthly" not in user_cols:
            await db.execute("ALTER TABLE economy_users ADD COLUMN last_monthly REAL DEFAULT 0")
        if "bank" in user_cols:
            await db.execute("""
                UPDATE economy_users
                SET bank_nodes = COALESCE(bank, 0)
                WHERE COALESCE(bank_nodes, 0) = 0 AND COALESCE(bank, 0) != 0
            """)

        log_cols = await EconomyDB._table_columns(db, "economy_logs")
        if "action_type" not in log_cols:
            await db.execute("ALTER TABLE economy_logs ADD COLUMN action_type TEXT")
        if "amount" not in log_cols:
            await db.execute("ALTER TABLE economy_logs ADD COLUMN amount INTEGER DEFAULT 0")
        if "details" not in log_cols:
            await db.execute("ALTER TABLE economy_logs ADD COLUMN details TEXT")
        if "timestamp" not in log_cols:
            await db.execute("ALTER TABLE economy_logs ADD COLUMN timestamp REAL")

    @staticmethod
    async def _ensure_passive_tables(db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS passive_rigs (
                user_id INTEGER PRIMARY KEY,
                miners INTEGER DEFAULT 0,
                gpus INTEGER DEFAULT 0,
                clusters INTEGER DEFAULT 0,
                quantum_servers INTEGER DEFAULT 0
            )
        """)

        rig_cols = await EconomyDB._table_columns(db, "passive_rigs")
        for column in ("miners", "gpus", "clusters", "quantum_servers"):
            if column not in rig_cols:
                await db.execute(f"ALTER TABLE passive_rigs ADD COLUMN {column} INTEGER DEFAULT 0")

    @staticmethod
    async def _ensure_inventory_tables(db: aiosqlite.Connection):
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy_inventory (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, item_id)
            )
        """)

    @staticmethod
    async def _table_columns(db: aiosqlite.Connection, table: str, schema: Optional[str] = None) -> set[str]:
        prefix = f"{schema}." if schema else ""
        async with db.execute(f"PRAGMA {prefix}table_info({table})") as cursor:
            rows = await cursor.fetchall()
        return {row[1] for row in rows}

    @staticmethod
    async def _table_exists(db: aiosqlite.Connection, table: str, schema: str = "main") -> bool:
        async with db.execute(
            f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ) as cursor:
            return await cursor.fetchone() is not None

    @staticmethod
    async def _maybe_migrate_legacy_data_db(db: aiosqlite.Connection):
        """Copy rows from the old ./data/economy.db if the root DB is empty."""
        if "ECONOMY_DB_PATH" in os.environ or not LEGACY_DATA_DB_PATH.exists():
            return

        current_path = Path(DB_PATH).resolve()
        if current_path == LEGACY_DATA_DB_PATH.resolve():
            return

        async with db.execute("SELECT COUNT(*) FROM economy_users") as cursor:
            current_users = (await cursor.fetchone())[0]
        if current_users:
            return

        async with aiosqlite.connect(str(LEGACY_DATA_DB_PATH)) as legacy:
            legacy.row_factory = aiosqlite.Row

            if await EconomyDB._table_exists(legacy, "economy_users"):
                async with legacy.execute("SELECT * FROM economy_users") as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    user = dict(row)
                    await db.execute("""
                        INSERT OR IGNORE INTO economy_users
                            (user_id, nodes, bank_nodes, last_daily, last_monthly)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        user.get("user_id"),
                        EconomyDB._to_int(user.get("nodes")),
                        EconomyDB._to_int(user.get("bank_nodes", user.get("bank"))),
                        user.get("last_daily") or 0,
                        user.get("last_monthly") or 0,
                    ))

            if await EconomyDB._table_exists(legacy, "economy_logs"):
                async with legacy.execute("SELECT * FROM economy_logs ORDER BY id ASC") as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    log = dict(row)
                    await db.execute("""
                        INSERT INTO economy_logs (user_id, action_type, amount, details, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        log.get("user_id"),
                        log.get("action_type"),
                        EconomyDB._to_int(log.get("amount")),
                        log.get("details"),
                        log.get("timestamp") or time.time(),
                    ))

            if await EconomyDB._table_exists(legacy, "passive_rigs"):
                async with legacy.execute("SELECT * FROM passive_rigs") as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    rig = dict(row)
                    await db.execute("""
                        INSERT OR IGNORE INTO passive_rigs
                            (user_id, miners, gpus, clusters, quantum_servers)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        rig.get("user_id"),
                        EconomyDB._to_int(rig.get("miners")),
                        EconomyDB._to_int(rig.get("gpus")),
                        EconomyDB._to_int(rig.get("clusters")),
                        EconomyDB._to_int(rig.get("quantum_servers")),
                    ))

    @staticmethod
    async def _register_user(db: aiosqlite.Connection, user_id: int):
        await db.execute("""
            INSERT OR IGNORE INTO economy_users (user_id, nodes, bank_nodes)
            VALUES (?, 0, 0)
        """, (user_id,))
        await db.execute("""
            INSERT OR IGNORE INTO passive_rigs (user_id)
            VALUES (?)
        """, (user_id,))

    @staticmethod
    async def register_user(user_id: int):
        """Create a user profile if it does not already exist."""
        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._register_user(db, user_id)
            await db.commit()

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_timestamp(value: Any) -> float:
        if value in (None, "", 0, "0"):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        try:
            return float(text)
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                return parsed.timestamp()
            except ValueError:
                continue

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def format_timestamp(value: Any) -> str:
        timestamp = EconomyDB._to_timestamp(value)
        if not timestamp:
            return "Unknown"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(timestamp))

    @staticmethod
    def _profile_from_row(row: Optional[aiosqlite.Row]) -> Optional[dict[str, Any]]:
        if row is None:
            return None

        data = dict(row)
        bank_nodes = data.get("bank_nodes", data.get("bank", 0))
        data["nodes"] = EconomyDB._to_int(data.get("nodes"))
        data["bank_nodes"] = EconomyDB._to_int(bank_nodes)
        data["bank"] = data["bank_nodes"]
        data["last_daily"] = EconomyDB._to_timestamp(data.get("last_daily"))
        data["last_monthly"] = EconomyDB._to_timestamp(data.get("last_monthly"))
        return data

    @staticmethod
    async def get_profile(user_id: int):
        """Fetch a user's wallet profile."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM economy_users WHERE user_id = ?", (user_id,)) as cursor:
                return EconomyDB._profile_from_row(await cursor.fetchone())

    @staticmethod
    async def get_user(user_id: int):
        """Ensure a user exists and return their profile."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await EconomyDB._register_user(db, user_id)
            await db.commit()
            async with db.execute("SELECT * FROM economy_users WHERE user_id = ?", (user_id,)) as cursor:
                return EconomyDB._profile_from_row(await cursor.fetchone())

    @staticmethod
    async def update_balance(
        user_id: int,
        nodes: int = 0,
        bank: int = 0,
        action_type: Optional[str] = None,
        details: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        """Update wallet or bank balances and optionally write an audit log.

        Supports the old command call style:
        update_balance(user_id, amount, "ACTION", "details")
        """
        if "amount" in kwargs and kwargs["amount"] is not None:
            nodes = kwargs["amount"]
        if "bank_nodes" in kwargs and kwargs["bank_nodes"] is not None:
            bank = kwargs["bank_nodes"]

        if isinstance(bank, str):
            details = action_type
            action_type = bank
            bank = 0

        nodes_delta = EconomyDB._to_int(nodes)
        bank_delta = EconomyDB._to_int(bank)

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await EconomyDB._register_user(db, user_id)

            async with db.execute(
                "SELECT nodes, bank_nodes FROM economy_users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                before = await cursor.fetchone()

            old_nodes = EconomyDB._to_int(before["nodes"])
            old_bank = EconomyDB._to_int(before["bank_nodes"])
            new_nodes = max(0, old_nodes + nodes_delta)
            new_bank = max(0, old_bank + bank_delta)
            actual_delta = (new_nodes - old_nodes) + (new_bank - old_bank)

            await db.execute("""
                UPDATE economy_users
                SET nodes = ?, bank_nodes = ?
                WHERE user_id = ?
            """, (new_nodes, new_bank, user_id))

            if action_type:
                await EconomyDB._log_transaction(db, user_id, action_type, actual_delta, details or "")

            await db.commit()
            return actual_delta

    @staticmethod
    async def update_bank_balance(
        user_id: int,
        amount: int,
        action_type: Optional[str] = None,
        details: Optional[str] = None,
    ) -> int:
        return await EconomyDB.update_balance(
            user_id=user_id,
            bank=amount,
            action_type=action_type,
            details=details,
        )

    @staticmethod
    async def set_balance(user_id: int, amount: int):
        amount = max(0, EconomyDB._to_int(amount))
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await EconomyDB._register_user(db, user_id)
            async with db.execute("SELECT nodes FROM economy_users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            old_amount = EconomyDB._to_int(row["nodes"] if row else 0)
            await db.execute("UPDATE economy_users SET nodes = ? WHERE user_id = ?", (amount, user_id))
            await EconomyDB._log_transaction(
                db,
                user_id,
                "ADMIN_SET",
                amount - old_amount,
                f"Wallet balance set to {amount}",
            )
            await db.commit()

    @staticmethod
    async def _log_transaction(
        db: aiosqlite.Connection,
        user_id: int,
        action_type: str,
        amount: int,
        details: str,
    ):
        await db.execute("""
            INSERT INTO economy_logs (user_id, action_type, amount, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, action_type, EconomyDB._to_int(amount), details, time.time()))

    @staticmethod
    async def log_transaction(user_id: int, action_type: str, amount: int, details: str):
        """Save a receipt of an economy action."""
        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._log_transaction(db, user_id, action_type, amount, details)
            await db.commit()

    @staticmethod
    async def get_history(user_id: int, limit: int = 5):
        """Fetch recent transactions for a user."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT action_type, amount, details, timestamp
                FROM economy_logs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (user_id, limit)) as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def add_item(user_id: int, item_id: str, quantity: int = 1):
        quantity = EconomyDB._to_int(quantity)
        if quantity <= 0:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._register_user(db, user_id)
            await db.execute("""
                INSERT INTO economy_inventory (user_id, item_id, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_id)
                DO UPDATE SET quantity = quantity + excluded.quantity
            """, (user_id, item_id, quantity))
            await db.commit()

    @staticmethod
    async def remove_item(user_id: int, item_id: str, quantity: int = 1) -> bool:
        quantity = EconomyDB._to_int(quantity)
        if quantity <= 0:
            return False

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT quantity
                FROM economy_inventory
                WHERE user_id = ? AND item_id = ?
            """, (user_id, item_id)) as cursor:
                row = await cursor.fetchone()

            current_quantity = EconomyDB._to_int(row[0] if row else 0)
            if current_quantity <= 0:
                return False

            new_quantity = max(0, current_quantity - quantity)
            if new_quantity:
                await db.execute("""
                    UPDATE economy_inventory
                    SET quantity = ?
                    WHERE user_id = ? AND item_id = ?
                """, (new_quantity, user_id, item_id))
            else:
                await db.execute("""
                    DELETE FROM economy_inventory
                    WHERE user_id = ? AND item_id = ?
                """, (user_id, item_id))
            await db.commit()
            return True

    @staticmethod
    async def get_item_count(user_id: int, item_id: str) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT quantity
                FROM economy_inventory
                WHERE user_id = ? AND item_id = ?
            """, (user_id, item_id)) as cursor:
                row = await cursor.fetchone()
        return EconomyDB._to_int(row[0] if row else 0)

    @staticmethod
    async def get_full_inventory(user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT item_id, quantity
                FROM economy_inventory
                WHERE user_id = ? AND quantity > 0
                ORDER BY item_id
            """, (user_id,)) as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def register_purchased_rig(user_id: int, rig_type: str, qty: int = 1):
        """Update passive hardware telemetry when a user buys a rig."""
        column_mapping = {
            "node_miner": "miners",
            "gpu_rig": "gpus",
            "ai_cluster": "clusters",
            "quantum_server": "quantum_servers",
        }
        col = column_mapping.get(rig_type)
        qty = EconomyDB._to_int(qty)
        if not col or qty <= 0:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._register_user(db, user_id)
            await db.execute(f"""
                INSERT INTO passive_rigs (user_id, {col})
                VALUES (?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET {col} = {col} + excluded.{col}
            """, (user_id, qty))
            await db.commit()

    @staticmethod
    async def process_global_income_tick():
        """Credit every registered passive mining rig."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT user_id, miners, gpus, clusters, quantum_servers
                FROM passive_rigs
            """) as cursor:
                rigs = await cursor.fetchall()

            for user_id, miners, gpus, clusters, quantums in rigs:
                hourly_yield = (
                    EconomyDB._to_int(miners) * 50
                    + EconomyDB._to_int(gpus) * 200
                    + EconomyDB._to_int(clusters) * 750
                    + EconomyDB._to_int(quantums) * 3500
                )

                if hourly_yield > 0:
                    await EconomyDB._register_user(db, user_id)
                    await db.execute("""
                        UPDATE economy_users
                        SET nodes = COALESCE(nodes, 0) + ?
                        WHERE user_id = ?
                    """, (hourly_yield, user_id))
                    await EconomyDB._log_transaction(
                        db,
                        user_id,
                        "PASSIVE_TICK",
                        hourly_yield,
                        "Automated hardware mining grid tick",
                    )
            await db.commit()

    @staticmethod
    async def update_cooldown(user_id: int, cooldown_type: str):
        """Update the timestamp when a user claims a timed reward."""
        columns = {"daily": "last_daily", "monthly": "last_monthly"}
        col = columns.get(cooldown_type)
        if not col:
            raise ValueError(f"Unknown cooldown type: {cooldown_type}")

        async with aiosqlite.connect(DB_PATH) as db:
            await EconomyDB._register_user(db, user_id)
            await db.execute(f"UPDATE economy_users SET {col} = ? WHERE user_id = ?", (time.time(), user_id))
            await db.commit()

    @staticmethod
    async def get_leaderboard(limit: int = 10):
        """Fetch top users by wallet plus bank assets."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT user_id, (COALESCE(nodes, 0) + COALESCE(bank_nodes, 0)) AS total_nodes
                FROM economy_users
                ORDER BY total_nodes DESC
                LIMIT ?
            """, (limit,)) as cursor:
                return await cursor.fetchall()
