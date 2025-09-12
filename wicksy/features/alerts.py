# alerts.py
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple, Optional

import aiosqlite
import discord
from discord.ext import tasks

from wicksy.db import DB_FILE
from wicksy.prices import normalize_symbol, get_crypto_price, get_stock_price
from wicksy.search import search_crypto, search_stock

# ---------- module state ----------
BOT_INSTANCE: Optional[discord.Client] = None
ALERTS_CHANNEL_ID: Optional[int] = None  # single public channel (fallback to DMs)
_ALERT_LOOP_STARTED = False
_ALERT_LOOP_LOCK = asyncio.Lock()

# cache: symbol -> (price, change, source, ts)
_PRICE_CACHE: Dict[
    str, Tuple[Optional[float], Optional[float], Optional[str], float]
] = {}
PRICE_CACHE_TTL = 55  # seconds (loop runs every ~60s)


# ---------- db helpers ----------
async def _ensure_schema():
    """Create tables if missing; add columns if needed; one-time & cheap."""
    async with aiosqlite.connect(DB_FILE) as db:
        # settings
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT
            )
            """
        )

        # alerts
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              symbol TEXT NOT NULL,
              target REAL NOT NULL,
              direction TEXT NOT NULL,  -- 'above' | 'below'
              created_at INTEGER DEFAULT (strftime('%s','now'))
            )
            """
        )

        # add "paused" column if missing
        cur = await db.execute("PRAGMA table_info(alerts)")
        cols = {row[1] for row in await cur.fetchall()}
        if "paused" not in cols:
            await db.execute("ALTER TABLE alerts ADD COLUMN paused INTEGER DEFAULT 0")

        await db.commit()


async def _restore_alert_channel():
    global ALERTS_CHANNEL_ID
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key='alerts_channel'")
        row = await cur.fetchone()
        if row:
            try:
                ALERTS_CHANNEL_ID = int(row[0])
            except Exception:
                ALERTS_CHANNEL_ID = None


# ---------- price helpers ----------
async def resolve_price(
    symbol: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Try crypto first (CoinGecko id), then stock (Yahoo). Return (price, change_24h, source)."""
    # crypto
    price, change = await get_crypto_price(symbol)
    if price is not None:
        return price, change, "crypto"
    # stock
    price, change = await get_stock_price(symbol)
    if price is not None:
        return price, change, "stock"
    return None, None, None


async def _get_price_cached(
    symbol: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    now = time.time()
    cached = _PRICE_CACHE.get(symbol)
    if cached and (now - cached[3] < PRICE_CACHE_TTL):
        return cached[0], cached[1], cached[2]
    price, change, source = await resolve_price(symbol)
    _PRICE_CACHE[symbol] = (price, change, source, now)
    return price, change, source


def _fmt_change(change: Optional[float]) -> str:
    if change is None:
        return ""
    try:
        arrow = "▲" if change >= 0 else "▼"
        return f"  ({arrow} {change:.2f}%)"
    except Exception:
        return ""


# ---------- messaging ----------
async def send_alert(
    user_id: int,
    symbol: str,
    price: float,
    target: float,
    direction: str,
    change: Optional[float] = None,
):
    """Send alert either to configured channel (if set) or DM the user."""
    global BOT_INSTANCE, ALERTS_CHANNEL_ID
    if not BOT_INSTANCE:
        return

    txt = (
        f"📢 **Alert triggered**\n"
        f"**{symbol}** is **{price:,.4f}**{_fmt_change(change)}, "
        f"which is **{direction} {target:,.4f}**."
    )

    # Prefer channel if configured and reachable
    if ALERTS_CHANNEL_ID:
        channel = BOT_INSTANCE.get_channel(ALERTS_CHANNEL_ID)
        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                await channel.send(f"<@{user_id}> {txt}")
                return
            except Exception:
                pass  # fall back to DM

    # DM fallback
    try:
        user = await BOT_INSTANCE.fetch_user(user_id)
        if user:
            await user.send(txt)
            return
    except Exception:
        pass

    # Last resort: first guild system channel (quietly)
    for guild in BOT_INSTANCE.guilds:
        if guild.system_channel:
            try:
                await guild.system_channel.send(f"<@{user_id}> {txt}")
                break
            except Exception:
                continue


# ---------- slash commands ----------
def setup_alerts(bot: discord.Client, guild_id: int):
    """Register the /alert command group and remember bot instance for the loop."""
    global BOT_INSTANCE
    BOT_INSTANCE = bot

    group = discord.app_commands.Group(name="alert", description="Price alerts")

    @group.command(
        name="setchannel", description="Set a channel for public alert notifications"
    )
    async def setchannel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        global ALERTS_CHANNEL_ID
        await _ensure_schema()
        ALERTS_CHANNEL_ID = channel.id
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("alerts_channel", str(channel.id)),
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ Alerts will post in {channel.mention} (DMs used if not set).",
            ephemeral=True,
        )

    @group.command(name="add", description="Create a price alert")
    @discord.app_commands.choices(
        direction=[
            discord.app_commands.Choice(name="above", value="above"),
            discord.app_commands.Choice(name="below", value="below"),
        ]
    )
    async def add(
        interaction: discord.Interaction,
        symbol: str,
        target: float,
        direction: discord.app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()

        clean = normalize_symbol(symbol)
        crypto_matches: List[str] = search_crypto(clean)
        stock_matches = search_stock(clean)  # list[dict]

        if crypto_matches:
            stored_symbol = crypto_matches[0]  # e.g., "bitcoin"
        elif stock_matches:
            stored_symbol = (
                stock_matches[0].get("symbol", clean).upper()
            )  # e.g., "AAPL"
        else:
            # No match — store normalized text but warn user
            stored_symbol = clean

        # De-dupe identical alert for same user
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM alerts WHERE user_id=? AND symbol=? AND target=? AND direction=?",
                (interaction.user.id, stored_symbol, target, direction.value),
            )
            await db.execute(
                "INSERT INTO alerts (user_id, symbol, target, direction, paused) VALUES (?, ?, ?, ?, 0)",
                (interaction.user.id, stored_symbol, target, direction.value),
            )
            await db.commit()

        warn = (
            ""
            if (crypto_matches or stock_matches)
            else "  _(heads up: I didn't find a known ticker/id; we'll still try it)_"
        )
        await interaction.followup.send(
            f"📌 Alert set for **{stored_symbol}** when price is **{direction.value} {target}**.{warn}",
            ephemeral=True,
        )

    # Autocomplete for the `symbol` param
    @add.autocomplete("symbol")
    async def alert_symbol_autocomplete(interaction: discord.Interaction, current: str):
        current = (current or "").strip()
        if not current:
            return []
        cryptos = search_crypto(current)[:5]  # list[str]
        stocks = search_stock(current)[:5]  # list[dict]

        values_seen = set()
        choices: List[discord.app_commands.Choice[str]] = []

        for c in cryptos:
            if c not in values_seen:
                values_seen.add(c)
                choices.append(
                    discord.app_commands.Choice(name=f"{c} (crypto)", value=c)
                )

        for s in stocks:
            symbol = s.get("symbol")
            if not symbol:
                continue
            name = s.get("name", symbol)
            if symbol not in values_seen:
                values_seen.add(symbol)
                choices.append(
                    discord.app_commands.Choice(
                        name=f"{name} ({symbol}) (stock)", value=symbol
                    )
                )

        return choices[:10]

    @group.command(name="list", description="Show your active alerts")
    async def list_alerts(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT id, symbol, target, direction, paused, created_at "
                "FROM alerts WHERE user_id=? ORDER BY id DESC",
                (interaction.user.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            await interaction.followup.send("You have no alerts.", ephemeral=True)
            return

        lines = ["**Your alerts:**"]
        for _id, sym, tgt, dirn, paused, created_at in rows:
            flag = "⏸️" if paused else "⏺️"
            lines.append(f"{flag} `#{_id}`  **{sym}**  {dirn}  {tgt}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Delete one alert by its ID")
    async def remove_alert(interaction: discord.Interaction, alert_id: int):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM alerts WHERE id=? AND user_id=?",
                (alert_id, interaction.user.id),
            )
            await db.commit()
        await interaction.followup.send(
            f"🗑️ Removed alert `#{alert_id}`.", ephemeral=True
        )

    @group.command(name="clear", description="Delete all your alerts")
    async def clear_alerts(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM alerts WHERE user_id=?", (interaction.user.id,)
            )
            await db.commit()
        await interaction.followup.send("🧹 All your alerts cleared.", ephemeral=True)

    @group.command(name="pause", description="Pause one alert by its ID")
    async def pause_alert(interaction: discord.Interaction, alert_id: int):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE alerts SET paused=1 WHERE id=? AND user_id=?",
                (alert_id, interaction.user.id),
            )
            await db.commit()
        await interaction.followup.send(
            f"⏸️ Paused alert `#{alert_id}`.", ephemeral=True
        )

    @group.command(name="resume", description="Resume one alert by its ID")
    async def resume_alert(interaction: discord.Interaction, alert_id: int):
        await interaction.response.defer(ephemeral=True)
        await _ensure_schema()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE alerts SET paused=0 WHERE id=? AND user_id=?",
                (alert_id, interaction.user.id),
            )
            await db.commit()
        await interaction.followup.send(
            f"▶️ Resumed alert `#{alert_id}`.", ephemeral=True
        )

    @group.command(
        name="test", description="Check current price for a symbol (no alert created)"
    )
    async def test_price(interaction: discord.Interaction, symbol: str):
        await interaction.response.defer(ephemeral=True)
        clean = normalize_symbol(symbol)
        price, change, source = await _get_price_cached(clean)
        if price is None:
            await interaction.followup.send(
                f"Couldn't resolve **{clean}** to a price.", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"**{clean}** → **{price:,.4f}**{_fmt_change(change)}  _(source: {source})_",
            ephemeral=True,
        )

    # Register the group for the guild
    bot.tree.add_command(group, guild=discord.Object(id=guild_id))

    # Run bootstrap AFTER the client is ready to avoid coroutine warnings
    async def _alerts_on_ready():
        await _ensure_schema()
        await _restore_alert_channel()
        _start_alert_loop_once()

    bot.add_listener(_alerts_on_ready, "on_ready")


def _start_alert_loop_once():
    global _ALERT_LOOP_STARTED
    if not _ALERT_LOOP_STARTED:
        try:
            alert_checker.start()
            _ALERT_LOOP_STARTED = True
        except RuntimeError:
            # If event loop not ready yet, we'll start on next setup call or when ready
            pass


# ---------- background checker ----------
@tasks.loop(minutes=1)
async def alert_checker():
    """Poll prices and fire alerts when thresholds are crossed."""
    global BOT_INSTANCE
    if not BOT_INSTANCE:
        return

    # Make sure schema (and the 'paused' column) exists before we query it
    await _ensure_schema()

    # ensure single run at a time
    if _ALERT_LOOP_LOCK.locked():
        return

    async with _ALERT_LOOP_LOCK:
        # 1) collect all active alerts
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT id, user_id, symbol, target, direction FROM alerts WHERE paused=0"
            )
            alerts = await cur.fetchall()

        if not alerts:
            return

        # 2) resolve unique symbols with caching (limits API load)
        unique_symbols = {row[2] for row in alerts}
        prices: Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]] = {}

        # limit concurrency to avoid hammering providers
        sem = asyncio.Semaphore(10)

        async def fetch_one(sym: str):
            async with sem:
                prices[sym] = await _get_price_cached(sym)

        await asyncio.gather(*(fetch_one(sym) for sym in unique_symbols))

        # 3) evaluate & collect to delete
        to_delete: List[int] = []
        for alert_id, user_id, symbol, target, direction in alerts:
            price, change, _ = prices.get(symbol, (None, None, None))
            if price is None:
                continue
            triggered = (direction == "above" and price >= target) or (
                direction == "below" and price <= target
            )
            if triggered:
                try:
                    await send_alert(user_id, symbol, price, target, direction, change)
                finally:
                    to_delete.append(alert_id)

        # 4) delete fired alerts
        if to_delete:
            async with aiosqlite.connect(DB_FILE) as db:
                await db.executemany(
                    "DELETE FROM alerts WHERE id=?", [(i,) for i in to_delete]
                )
                await db.commit()
