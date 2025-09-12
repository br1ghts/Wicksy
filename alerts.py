# alerts.py
import discord
import aiosqlite
from discord.ext import tasks
from typing import List
from prices import normalize_symbol, get_crypto_price, get_stock_price
from search import search_crypto, search_stock
from db import DB_FILE

BOT_INSTANCE: discord.Client | None = None
ALERTS_CHANNEL_ID: int | None = None  # optional: post alerts in a channel; otherwise DM


# ---------- helpers ----------
async def resolve_price(symbol: str):
    """Try crypto first (CoinGecko id), then stock (Yahoo). Return (price, change, source)."""
    price, change = await get_crypto_price(symbol)
    if price is not None:
        return price, change, "crypto"
    price, change = await get_stock_price(symbol)
    if price is not None:
        return price, change, "stock"
    return None, None, None


async def send_alert(
    user_id: int, symbol: str, price: float, target: float, direction: str
):
    """Send alert either to configured channel (if set) or DM the user."""
    global BOT_INSTANCE, ALERTS_CHANNEL_ID
    if not BOT_INSTANCE:
        return

    txt = f"📢 **Alert triggered**\n**{symbol}** is **{price:,.2f}**, which is **{direction} {target:,.2f}**."

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
    except Exception:
        # As a last resort try sending to first available guild system channel (quietly)
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
    global BOT_INSTANCE, ALERTS_CHANNEL_ID
    BOT_INSTANCE = bot

    group = discord.app_commands.Group(name="alert", description="Price alerts")

    @group.command(
        name="setchannel", description="Set a channel for public alert notifications"
    )
    async def setchannel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        global ALERTS_CHANNEL_ID
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

        clean = normalize_symbol(symbol)

        # Prefer crypto first, then stock
        crypto_matches: List[str] = search_crypto(clean)
        stock_matches = search_stock(clean)  # list[dict]

        if crypto_matches:
            stored_symbol = crypto_matches[0]  # e.g. "bitcoin"
        elif stock_matches:
            stored_symbol = stock_matches[0]["symbol"]  # e.g. "AAPL"
        else:
            stored_symbol = clean  # fallback if nothing found

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO alerts (user_id, symbol, target, direction) VALUES (?, ?, ?, ?)",
                (interaction.user.id, stored_symbol, target, direction.value),
            )
            await db.commit()

        await interaction.followup.send(
            f"📌 Alert set for **{stored_symbol}** when price is **{direction.value} {target}**.",
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
        choices = []

        for c in cryptos:
            if c not in values_seen:
                values_seen.add(c)
                choices.append(
                    discord.app_commands.Choice(name=f"{c} (crypto)", value=c)
                )

        for s in stocks:
            try:
                symbol = s["symbol"]
                name = s.get("name", symbol)
            except Exception:
                continue
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
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT id, symbol, target, direction FROM alerts WHERE user_id=? ORDER BY id DESC",
                (interaction.user.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            await interaction.followup.send("You have no alerts.", ephemeral=True)
            return

        lines = ["**Your alerts:**"]
        for _id, sym, tgt, dirn in rows:
            lines.append(f"`#{_id}`  **{sym}**  {dirn}  {tgt}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Delete one alert by its ID")
    async def remove_alert(interaction: discord.Interaction, alert_id: int):
        await interaction.response.defer(ephemeral=True)
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
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM alerts WHERE user_id=?", (interaction.user.id,)
            )
            await db.commit()
        await interaction.followup.send("🧹 All your alerts cleared.", ephemeral=True)

    # Load alerts_channel from DB (optional)
    async def _restore_alert_channel():
        global ALERTS_CHANNEL_ID
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key='alerts_channel'"
            )
            row = await cur.fetchone()
            if row:
                ALERTS_CHANNEL_ID = int(row[0])

    bot.tree.add_command(group, guild=discord.Object(id=guild_id))


# ---------- background checker ----------
@tasks.loop(minutes=1)
async def alert_checker():
    """Poll prices and fire alerts when thresholds are crossed."""
    global BOT_INSTANCE
    if not BOT_INSTANCE:
        return

    # 1) collect all alerts
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT id, user_id, symbol, target, direction FROM alerts"
        )
        alerts = await cur.fetchall()

    if not alerts:
        return

    # 2) evaluate
    to_delete: list[int] = []
    for alert_id, user_id, symbol, target, direction in alerts:
        price, _, _ = await resolve_price(symbol)
        if price is None:
            continue

        triggered = (direction == "above" and price >= target) or (
            direction == "below" and price <= target
        )
        if triggered:
            try:
                await send_alert(user_id, symbol, price, target, direction)
            finally:
                to_delete.append(alert_id)

    # 3) delete fired alerts
    if to_delete:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.executemany(
                "DELETE FROM alerts WHERE id=?", [(i,) for i in to_delete]
            )
            await db.commit()
