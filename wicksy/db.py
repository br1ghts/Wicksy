import aiosqlite

DB_FILE = "Wicksy.db"


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                target REAL,
                direction TEXT
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                notes TEXT
            )"""
        )
        # ✅ Add "type" column to watchlist so we can separate crypto vs stocks
        await db.execute(
            """CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE,
                type TEXT CHECK(type IN ('crypto','stock')) NOT NULL DEFAULT 'stock'
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )

        # ✅ Migration: if old table exists without "type", add it
        try:
            await db.execute(
                "ALTER TABLE watchlist ADD COLUMN type TEXT DEFAULT 'stock'"
            )
        except Exception:
            # Ignore if column already exists
            pass

        await db.commit()
