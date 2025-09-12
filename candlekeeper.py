import os
import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
from dotenv import load_dotenv
from discord import app_commands

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "candlekeeper.db"


# ------------- Database Setup -----------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                target REAL,
                direction TEXT
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                notes TEXT
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE
            )
        """
        )
        await db.commit()


# ------------- Events -----------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await init_db()
    try:
        synced = await bot.tree.sync()
        print(f"🔗 Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"⚠️ Slash command sync failed: {e}")
    watchlist_updater.start()


# ------------- Slash Commands -----------------
@bot.tree.command(name="price", description="Manage price alerts")
async def price(
    interaction: discord.Interaction,
    action: str,
    symbol: str = None,
    target: float = None,
    direction: str = "above",
):
    if action == "add" and symbol and target:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO alerts (user_id, symbol, target, direction) VALUES (?, ?, ?, ?)",
                (interaction.user.id, symbol.upper(), target, direction),
            )
            await db.commit()
        await interaction.response.send_message(
            f"📈 Alert added for **{symbol.upper()}** at {target} ({direction})"
        )
    elif action == "list":
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "SELECT symbol, target, direction FROM alerts WHERE user_id=?",
                (interaction.user.id,),
            )
            rows = await cursor.fetchall()
        if rows:
            msg = "\n".join([f"{s} {d} {t}" for s, t, d in rows])
            await interaction.response.send_message(f"Your alerts:\n{msg}")
        else:
            await interaction.response.send_message("No alerts found.")
    else:
        await interaction.response.send_message(
            "Usage: /price add SYMBOL TARGET [direction=above/below] | /price list"
        )


@bot.tree.command(name="trade", description="Post or manage trades")
async def trade(
    interaction: discord.Interaction,
    action: str,
    symbol: str = None,
    entry: float = None,
    sl: float = None,
    tp: float = None,
    notes: str = None,
):
    if action == "add" and all([symbol, entry, sl, tp]):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO trades (user_id, symbol, entry, sl, tp, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, symbol.upper(), entry, sl, tp, notes or ""),
            )
            await db.commit()
        embed = discord.Embed(
            title=f"📊 Trade Idea: {symbol.upper()}", color=discord.Color.blue()
        )
        embed.add_field(name="Entry", value=str(entry))
        embed.add_field(name="Stop Loss", value=str(sl))
        embed.add_field(name="Take Profit", value=str(tp))
        if notes:
            embed.add_field(name="Notes", value=notes, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "Usage: /trade add SYMBOL ENTRY SL TP [NOTES]"
        )


@bot.tree.command(name="watchlist", description="Manage your shared watchlist")
async def watchlist(interaction: discord.Interaction, action: str, symbol: str = None):
    if action == "add" and symbol:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT OR IGNORE INTO watchlist (symbol) VALUES (?)", (symbol.upper(),)
            )
            await db.commit()
        await interaction.response.send_message(
            f"🔍 Added {symbol.upper()} to watchlist"
        )
    elif action == "remove" and symbol:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.upper(),))
            await db.commit()
        await interaction.response.send_message(
            f"❌ Removed {symbol.upper()} from watchlist"
        )
    elif action == "list":
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("SELECT symbol FROM watchlist")
            rows = await cursor.fetchall()
        if rows:
            await interaction.response.send_message(
                "📋 Watchlist: " + ", ".join([r[0] for r in rows])
            )
        else:
            await interaction.response.send_message("Watchlist is empty.")
    else:
        await interaction.response.send_message(
            "Usage: /watchlist add SYMBOL | remove SYMBOL | list"
        )


# ------------- Background Tasks -----------------
@tasks.loop(minutes=5)
async def watchlist_updater():
    """Placeholder for auto-updating the watchlist embed every 5 minutes"""
    print("⏳ Watchlist update tick")
    # TODO: fetch prices, update message


# ------------- Run -----------------
if TOKEN is None:
    raise ValueError("❌ DISCORD_TOKEN is not set in the environment or .env file")

bot.run(TOKEN)
