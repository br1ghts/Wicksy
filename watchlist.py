import discord
import aiosqlite
from discord.ext import tasks
from prices import normalize_symbol, get_crypto_price, get_stock_price
from search import search_crypto, search_stock
from db import DB_FILE

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
        await interaction.response.send_message(
            f"✅ Watchlist channel set to {channel.mention}", ephemeral=True
        )

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
        clean = normalize_symbol(symbol)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM watchlist WHERE symbol=?", (clean,))
            await db.commit()
        await interaction.followup.send(f"❌ Removed {clean}", ephemeral=True)

    @group.command(name="clear")
    async def clear(interaction: discord.Interaction):
        global WATCHLIST_MESSAGE_ID
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM watchlist")
            await db.commit()
        WATCHLIST_MESSAGE_ID = None
        await interaction.followup.send("🧹 Watchlist cleared.", ephemeral=True)

    @group.command(name="list")
    async def listcmd(interaction: discord.Interaction):
        global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID
        await interaction.response.defer(ephemeral=False)

        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT symbol, type FROM watchlist")
            rows = await cur.fetchall()

        if not rows:
            await interaction.followup.send("Empty watchlist.")
            return

        table_str = await build_watchlist_table(rows)
        embed = discord.Embed(
            title="📋 CandleKeeper Watchlist",
            description=table_str,
            color=discord.Color.green(),
        )

        if not WATCHLIST_CHANNEL_ID:
            await interaction.followup.send("⚠️ Use `/watchlist setchannel` first.")
            return

        channel = bot.get_channel(WATCHLIST_CHANNEL_ID)
        if not channel:
            await interaction.followup.send("⚠️ Channel not found.")
            return

        if WATCHLIST_MESSAGE_ID:
            try:
                msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
                await msg.edit(embed=embed)
            except:
                WATCHLIST_MESSAGE_ID = None
        if not WATCHLIST_MESSAGE_ID:
            msg = await channel.send(embed=embed)
            WATCHLIST_MESSAGE_ID = msg.id
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("watchlist_message", str(WATCHLIST_MESSAGE_ID)),
                )
                await db.commit()

        await interaction.followup.send(f"✅ Watchlist updated in {channel.mention}")

    bot.tree.add_command(group, guild=discord.Object(id=guild_id))


@tasks.loop(minutes=1)
async def updater():
    global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID, BOT_INSTANCE
    if not WATCHLIST_CHANNEL_ID or not BOT_INSTANCE:
        return
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT symbol, type FROM watchlist")
        rows = await cur.fetchall()
    if not rows:
        return

    table_str = await build_watchlist_table(rows)
    embed = discord.Embed(
        title="📋 CandleKeeper Watchlist",
        description=table_str,
        color=discord.Color.green(),
    )

    channel = BOT_INSTANCE.get_channel(WATCHLIST_CHANNEL_ID)
    if not channel:
        return

    if WATCHLIST_MESSAGE_ID:
        try:
            msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
            await msg.edit(embed=embed)
            return
        except:
            WATCHLIST_MESSAGE_ID = None

    msg = await channel.send(embed=embed)
    WATCHLIST_MESSAGE_ID = msg.id
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("watchlist_message", str(WATCHLIST_MESSAGE_ID)),
        )
        await db.commit()
