import discord
import aiosqlite
from discord.ext import tasks
from wicksy.prices import normalize_symbol, get_crypto_price, get_stock_price
from wicksy.search import search_crypto, search_stock
from wicksy.db import DB_FILE

WATCHLIST_CHANNEL_ID = None
WATCHLIST_MESSAGE_ID = None
BOT_INSTANCE = None  # store bot here so updater can use it


async def build_watchlist_table(rows):
    lines = []
    header = f"{'SYMBOL':<10} | {'PRICE':<12} | {'CHANGE':<8}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)

    for symbol, asset_type in rows:
        if asset_type == "crypto":
            price, change = await get_crypto_price(symbol)  # CoinGecko ID
            display_symbol = symbol.upper()
        else:
            price, change = await get_stock_price(symbol)  # stock ticker
            display_symbol = symbol.upper()

        price_str = f"${price:,.2f}" if price is not None else "❓"
        if change is not None:
            arrow = "🔺" if change >= 0 else "🔻"
            change_str = f"{arrow}{abs(change):.2f}%"
        else:
            change_str = "N/A"

        lines.append(f"{display_symbol:<10} | {price_str:<12} | {change_str:<8}")

    return "```\n" + "\n".join(lines) + "\n```"


async def upsert_watchlist_message():
    """Create or update the watchlist message in the configured channel.

    - Reads rows from DB
    - Builds an embed table
    - Edits existing message if we have the ID, otherwise sends a new one
    - Persists the message ID in settings
    """
    global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID, BOT_INSTANCE

    if not BOT_INSTANCE or not WATCHLIST_CHANNEL_ID:
        return False

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT symbol, type FROM watchlist")
        rows = await cur.fetchall()

    # If no symbols, leave (do not create/update a message)
    if not rows:
        return False

    table_str = await build_watchlist_table(rows)
    embed = discord.Embed(
        title="📋 Wicksy Watchlist",
        description=table_str,
        color=discord.Color.green(),
    )

    channel = BOT_INSTANCE.get_channel(WATCHLIST_CHANNEL_ID)
    if not channel:
        return False

    # Try to edit existing message if we have it
    if WATCHLIST_MESSAGE_ID:
        try:
            msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
            await msg.edit(embed=embed)
            return True
        except Exception:
            WATCHLIST_MESSAGE_ID = None

    # Otherwise send a fresh one and persist the new ID
    msg = await channel.send(embed=embed)
    WATCHLIST_MESSAGE_ID = msg.id
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("watchlist_message", str(WATCHLIST_MESSAGE_ID)),
        )
        await db.commit()

    return True


def setup_watchlist(bot, guild_id):
    global BOT_INSTANCE
    BOT_INSTANCE = bot

    group = discord.app_commands.Group(
        name="watchlist", description="Manage your shared watchlist"
    )

    @group.command(name="setchannel")
    async def setchannel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        global WATCHLIST_CHANNEL_ID
        WATCHLIST_CHANNEL_ID = channel.id
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("watchlist_channel", str(channel.id)),
            )
            await db.commit()
        # Try to render or update the message in the new channel immediately
        await interaction.response.send_message(
            f"✅ Watchlist channel set to {channel.mention}", ephemeral=True
        )
        await upsert_watchlist_message()

    @group.command(name="add")
    async def add(interaction: discord.Interaction, symbol: str):
        await interaction.response.defer(ephemeral=True)

        # Determine type based on DB search
        if symbol.lower() in [c.lower() for c in search_crypto(symbol)]:
            asset_type = "crypto"
            saved_symbol = symbol.lower()  # CoinGecko ID
        else:
            asset_type = "stock"
            saved_symbol = symbol.upper()  # Stock ticker

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR IGNORE INTO watchlist (symbol, type) VALUES (?, ?)",
                (saved_symbol, asset_type),
            )
            await db.commit()

        await interaction.followup.send(
            f"🔍 Added `{saved_symbol}` as {asset_type}", ephemeral=True
        )
        # Update the watchlist message if channel configured
        await upsert_watchlist_message()

    # Autocomplete shows pretty labels but saves clean IDs/tickers
    @add.autocomplete("symbol")
    async def autocomplete(interaction: discord.Interaction, current: str):
        crypto = search_crypto(current)  # returns CoinGecko IDs
        stocks = search_stock(current)  # returns dicts with "symbol" + "name"

        choices = []
        for c in crypto:
            choices.append(discord.app_commands.Choice(name=c.capitalize(), value=c))
        for s in stocks:
            choices.append(
                discord.app_commands.Choice(
                    name=f"{s['name']} ({s['symbol']})",
                    value=s["symbol"],  # ✅ only save ticker
                )
            )
        return choices[:10]

    @group.command(name="remove")
    async def remove(interaction: discord.Interaction, symbol: str):
        await interaction.response.defer(ephemeral=True)
        # Be flexible about case. Crypto IDs are typically lowercase, stocks uppercase.
        # Use a case-insensitive delete to cover both.
        clean = symbol.strip()
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM watchlist WHERE symbol = ? COLLATE NOCASE",
                (clean,),
            )
            await db.commit()
        await interaction.followup.send(f"❌ Removed {clean}", ephemeral=True)
        await upsert_watchlist_message()

    @group.command(name="clear")
    async def clear(interaction: discord.Interaction):
        global WATCHLIST_MESSAGE_ID, WATCHLIST_CHANNEL_ID
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM watchlist")
            await db.commit()
        # Try to delete the existing watchlist message in the channel, if present
        if WATCHLIST_CHANNEL_ID and WATCHLIST_MESSAGE_ID and BOT_INSTANCE:
            channel = BOT_INSTANCE.get_channel(WATCHLIST_CHANNEL_ID)
            if channel:
                try:
                    msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
                    await msg.delete()
                except Exception:
                    pass
        WATCHLIST_MESSAGE_ID = None
        # Clear message ID from settings as well
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM settings WHERE key='watchlist_message'")
            await db.commit()
        await interaction.followup.send("🧹 Watchlist cleared.", ephemeral=True)

    @group.command(name="list")
    async def listcmd(interaction: discord.Interaction):
        global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID
        await interaction.response.defer(ephemeral=False)

        # Ensure a channel is configured
        if not WATCHLIST_CHANNEL_ID:
            await interaction.followup.send("⚠️ Use `/watchlist setchannel` first.")
            return

        # Update or create the message and provide confirmation
        updated = await upsert_watchlist_message()
        if not updated:
            await interaction.followup.send("Empty watchlist.")
            return

        channel = bot.get_channel(WATCHLIST_CHANNEL_ID)
        await interaction.followup.send(f"✅ Watchlist updated in {channel.mention}")

    bot.tree.add_command(group, guild=discord.Object(id=guild_id))


@tasks.loop(minutes=1)
async def updater():
    global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID, BOT_INSTANCE
    if not WATCHLIST_CHANNEL_ID or not BOT_INSTANCE:
        return
    await upsert_watchlist_message()
