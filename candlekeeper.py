import os
import re
import discord
from discord.ext import commands, tasks
import aiosqlite
from dotenv import load_dotenv
import yfinance as yf
import requests

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "candlekeeper.db"

WATCHLIST_MESSAGE_ID = None
WATCHLIST_CHANNEL_ID = None

# ⚡ Your dev guild/server ID
GUILD_ID = 1403372385490436187


# ---------------- Database ----------------
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
        await db.execute(
            """CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        await db.commit()


# ---------------- Helpers ----------------
def normalize_symbol(symbol: str) -> str:
    match = re.search(r"\(([^)]+)\)", symbol)
    if match:
        return match.group(1).upper()
    return symbol.upper().strip()


async def get_crypto_price(symbol: str):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": symbol.lower(),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if symbol.lower() in data:
            price = data[symbol.lower()]["usd"]
            change = data[symbol.lower()]["usd_24h_change"]
            return price, change
    except Exception as e:
        print(f"⚠️ Crypto fetch error {symbol}: {e}")
    return None, None


async def get_stock_price(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="2d")
        if not data.empty:
            price = data["Close"].iloc[-1]
            prev_close = data["Close"].iloc[-2] if len(data) > 1 else price
            change = ((price - prev_close) / prev_close) * 100
            return price, change
    except Exception as e:
        print(f"⚠️ Stock fetch error {symbol}: {e}")
    return None, None


def search_crypto(query: str):
    try:
        url = "https://api.coingecko.com/api/v3/search"
        resp = requests.get(url, params={"query": query}, timeout=5)
        results = resp.json().get("coins", [])
        return [c["id"] for c in results[:5]]
    except Exception as e:
        print(f"⚠️ Crypto search failed: {e}")
        return []


def search_stock(query: str):
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params={"q": query}, headers=headers, timeout=5)
        if resp.status_code != 200:
            return []
        results = resp.json().get("quotes", [])
        return [
            f"{q.get('shortname', q.get('symbol', 'Unknown'))} ({q['symbol']})"
            for q in results[:5]
            if "symbol" in q
        ]
    except Exception as e:
        print(f"⚠️ Stock search failed: {e}")
        return []


async def build_watchlist_table(rows):
    lines = []
    header = f"{'SYMBOL':<8} | {'PRICE':<12} | {'CHANGE':<8}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)

    for r in rows:
        symbol = r[0]
        price, change = await get_crypto_price(symbol)
        if price is None:
            price, change = await get_stock_price(symbol)
        if price:
            arrow = "🔺" if change and change >= 0 else "🔻"
            line = f"{symbol:<8} | ${price:<12,.2f} | {arrow}{change:.2f}%"
        else:
            line = f"{symbol:<8} | {'❓':<12} | N/A"
        lines.append(line)

    return "```\n" + "\n".join(lines) + "\n```"


# ---------------- Events ----------------
@bot.event
async def on_ready():
    global WATCHLIST_CHANNEL_ID, WATCHLIST_MESSAGE_ID
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await init_db()

    try:
        guild_obj = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild_obj)
        print(f"🔗 Synced commands to {GUILD_ID}")

        # Restore saved settings
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key='watchlist_channel'"
            )
            row = await cur.fetchone()
            if row:
                WATCHLIST_CHANNEL_ID = int(row[0])
            cur = await db.execute(
                "SELECT value FROM settings WHERE key='watchlist_message'"
            )
            row = await cur.fetchone()
            if row:
                WATCHLIST_MESSAGE_ID = int(row[0])
    except Exception as e:
        print(f"⚠️ Sync failed: {e}")

    watchlist_updater.start()


# ---------------- Watchlist Commands ----------------
watchlist_group = discord.app_commands.Group(
    name="watchlist", description="Manage watchlist"
)


@watchlist_group.command(
    name="setchannel", description="Set the channel for watchlist updates"
)
async def watchlist_setchannel(
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


@watchlist_group.command(name="add", description="Add an asset to the watchlist")
async def watchlist_add(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer(ephemeral=True)
    clean_symbol = normalize_symbol(symbol)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO watchlist (symbol) VALUES (?)", (clean_symbol,)
        )
        await db.commit()
    await interaction.followup.send(
        f"🔍 Added {clean_symbol} to watchlist", ephemeral=True
    )


@watchlist_add.autocomplete("symbol")
async def watchlist_symbol_autocomplete(interaction: discord.Interaction, current: str):
    crypto = search_crypto(current)
    stocks = search_stock(current)
    suggestions = list(dict.fromkeys(crypto + stocks))
    return [
        discord.app_commands.Choice(name=s, value=normalize_symbol(s))
        for s in suggestions[:10]
    ]


@watchlist_group.command(name="list", description="Show the watchlist table")
async def watchlist_list(interaction: discord.Interaction):
    global WATCHLIST_MESSAGE_ID, WATCHLIST_CHANNEL_ID
    await interaction.response.defer(ephemeral=False)

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT symbol FROM watchlist")
        rows = await cur.fetchall()

    if not rows:
        await interaction.followup.send("Watchlist is empty.")
        return

    table_str = await build_watchlist_table(rows)
    embed = discord.Embed(
        title="📋 CandleKeeper Watchlist",
        description=table_str,
        color=discord.Color.green(),
    )

    if not WATCHLIST_CHANNEL_ID:
        await interaction.followup.send(
            "⚠️ No channel set. Use `/watchlist setchannel` first."
        )
        return

    channel = bot.get_channel(WATCHLIST_CHANNEL_ID)
    if not channel:
        await interaction.followup.send("⚠️ Could not find the set channel.")
        return

    try:
        if WATCHLIST_MESSAGE_ID:
            msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
            await msg.edit(embed=embed)
        else:
            msg = await channel.send(embed=embed)
            WATCHLIST_MESSAGE_ID = msg.id
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("watchlist_message", str(WATCHLIST_MESSAGE_ID)),
                )
                await db.commit()
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to post: {e}")
        return

    await interaction.followup.send(f"✅ Watchlist updated in {channel.mention}")


bot.tree.add_command(watchlist_group, guild=discord.Object(id=GUILD_ID))


# ---------------- Background Updater ----------------
@tasks.loop(minutes=1)
async def watchlist_updater():
    global WATCHLIST_MESSAGE_ID, WATCHLIST_CHANNEL_ID
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT symbol FROM watchlist")
        rows = await cur.fetchall()
    if not WATCHLIST_CHANNEL_ID or not rows:
        return

    table_str = await build_watchlist_table(rows)
    embed = discord.Embed(
        title="📋 CandleKeeper Watchlist",
        description=table_str,
        color=discord.Color.green(),
    )

    channel = bot.get_channel(WATCHLIST_CHANNEL_ID)
    if not channel:
        return

    try:
        if WATCHLIST_MESSAGE_ID:
            msg = await channel.fetch_message(WATCHLIST_MESSAGE_ID)
            await msg.edit(embed=embed)
        else:
            msg = await channel.send(embed=embed)
            WATCHLIST_MESSAGE_ID = msg.id
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    ("watchlist_message", str(WATCHLIST_MESSAGE_ID)),
                )
                await db.commit()
    except Exception as e:
        print(f"⚠️ Watchlist update failed: {e}")


# ---------------- Run ----------------
if TOKEN is None:
    raise ValueError("❌ DISCORD_TOKEN is not set in the environment or .env file")
bot.run(TOKEN)
