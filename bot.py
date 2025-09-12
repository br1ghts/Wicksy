import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import init_db
from watchlist import (
    setup_watchlist,
    updater,
    WATCHLIST_CHANNEL_ID,
    WATCHLIST_MESSAGE_ID,
)

# from trades import setup_trades
# from alerts import setup_alerts

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = 1403372385490436187


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    # make sure DB exists
    await init_db()

    # sync commands for guild
    guild_obj = discord.Object(id=GUILD_ID)
    synced = await bot.tree.sync(guild=guild_obj)
    print(f"🔗 Synced {len(synced)} guild slash commands to {GUILD_ID}")

    # ✅ start background updater only once the bot is ready
    if not updater.is_running():
        updater.start()
        print("🟢 Watchlist updater started")

    # restore state from DB for channel/message IDs
    import aiosqlite

    async with aiosqlite.connect("candlekeeper.db") as db:
        cur = await db.execute(
            "SELECT value FROM settings WHERE key='watchlist_channel'"
        )
        row = await cur.fetchone()
        if row:
            globals()["WATCHLIST_CHANNEL_ID"] = int(row[0])

        cur = await db.execute(
            "SELECT value FROM settings WHERE key='watchlist_message'"
        )
        row = await cur.fetchone()
        if row:
            globals()["WATCHLIST_MESSAGE_ID"] = int(row[0])


# Register features before running
setup_watchlist(bot, GUILD_ID)
# setup_trades(bot, GUILD_ID)
# setup_alerts(bot, GUILD_ID)


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("❌ DISCORD_TOKEN not set in .env")
    bot.run(TOKEN)
