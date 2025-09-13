import aiosqlite
from wicksy.db import DB_FILE


async def get_trades() -> list[dict]:
    """Return all stored trades."""
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, user_id, symbol, entry, sl, tp, notes FROM trades"
        )
        rows = await cur.fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "symbol": row[2],
            "entry": row[3],
            "sl": row[4],
            "tp": row[5],
            "notes": row[6],
        }
        for row in rows
    ]
