# Wicksy Bot — Usage Guide

This guide walks you through installing, configuring, and using Wicksy’s slash commands for the Watchlist and Alerts features.

---

## Quick Start

- Requirements: Python 3.10+, a Discord bot token, and permission to invite the bot to your server.
- Create `.env` at the project root with:
  
  ```
  DISCORD_TOKEN=your_discord_bot_token
  ```

- Install dependencies and run:
  
  ```bash
  python3 -m venv venv
  source venv/bin/activate  # or venv\Scripts\activate on Windows
  pip install -r requirements.txt
  python3 run.py
  ```

- First run output shows when slash commands sync, e.g.:
  
  - Logged in as <botname>
  - Synced N guild slash commands
  - Watchlist updater started
  - Alert checker started

Note: In this codebase, commands are registered to a specific server via `GUILD_ID` in `wicksy/bot.py`. Set that to your server’s ID before running.

---

## Permissions

Ensure the bot role has these permissions in the target channels:
- Send Messages
- Embed Links
- Read Message History

No privileged message content intent is required; Wicksy uses slash commands.

---

## Watchlist Commands

Group: `/watchlist`

- `/watchlist setchannel #channel`
  - Select the channel where the live watchlist message is posted/updated.
- `/watchlist add symbol:<value>`
  - Adds a crypto (CoinGecko id) or a stock (ticker) to the shared list.
  - Autocomplete provides suggestions for both.
- `/watchlist list`
  - Creates or updates the pinned watchlist message in the configured channel.
- `/watchlist remove symbol:<value>`
  - Removes one entry. Case-insensitive.
- `/watchlist clear`
  - Empties the list and removes the posted message.

Behavior:
- The watchlist message auto-refreshes approximately every minute with fresh prices.
- Crypto symbols are stored as CoinGecko ids (e.g., `bitcoin`), stocks as tickers (e.g., `AAPL`).

---

## Alerts Commands

Group: `/alert`

- `/alert setchannel #channel` (optional)
  - Sets a public channel for alert notifications; if not set, alerts DM the user.
- `/alert add symbol:<value> target:<number> direction:<above|below>`
  - Creates an alert that triggers when the price crosses above/below the target.
  - Autocomplete provides stock and crypto suggestions.
- `/alert list`
  - Lists your active alerts. Paused alerts show a pause indicator.
- `/alert remove alert_id:<id>`
  - Removes a single alert by its id.
- `/alert clear`
  - Removes all your alerts.
- `/alert pause alert_id:<id>` / `/alert resume alert_id:<id>`
  - Temporarily stop/resume a specific alert.
- `/alert test symbol:<value>`
  - Shows the current price and 24h change without creating an alert.

Behavior:
- The alert checker runs about once per minute and deletes alerts after triggering.
- Alerts prefer the configured alerts channel; if unavailable, the bot DMs you.

---

## Data & Persistence

- SQLite database file: `Wicksy.db` (default, at repo root).
- Tables used:
  - `settings` — stores IDs for watchlist/alerts channels and watchlist message id.
  - `watchlist` — shared list of symbols with type (`crypto` or `stock`).
  - `alerts` — user alerts with target and direction (includes a `paused` flag).

---

## Troubleshooting

- Slash commands don’t appear:
  - Confirm `GUILD_ID` in `wicksy/bot.py` matches your server id.
  - The bot must be invited with the `applications.commands` scope.
  - Wait up to a minute after startup; check logs for the “Synced … commands” line.

- Watchlist message not updating:
  - Run `/watchlist setchannel` and then `/watchlist list` once.
  - Ensure the bot can Embed Links in that channel.

- No price for a symbol:
  - For crypto, use CoinGecko ids (e.g., `bitcoin`, `ethereum`).
  - For stocks, use the exchange ticker (e.g., `AAPL`, `TSLA`).

- Alerts not firing:
  - Check logs for “Alert checker started”.
  - Verify the target and direction (above/below) and that the symbol resolves.
  - If DMs are closed and no alerts channel is set, you might not receive alerts.

---

## Tips

- Use autocomplete to avoid typos in symbols.
- After moving the watchlist to a new channel, run `/watchlist list` to re-post if empty.
- You can pause alerts instead of removing them when you just need a break.

