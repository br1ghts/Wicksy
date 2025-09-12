# Slash Commands Reference

## /watchlist
- `setchannel channel:<#channel>`: Set the channel where the live watchlist message is posted.
- `add symbol:<text>`: Add a crypto (CoinGecko id) or stock ticker.
- `list`: Create or update the watchlist message in the configured channel.
- `remove symbol:<text>`: Remove an entry (case-insensitive).
- `clear`: Clear all entries and delete the watchlist message.

Notes:
- The watchlist auto-updates roughly every minute.
- Crypto ids are lowercase (e.g., `bitcoin`); stock tickers are uppercase (e.g., `AAPL`).

## /alert
- `setchannel channel:<#channel>`: Configure a public channel for alert notifications (optional).
- `add symbol:<text> target:<number> direction:<above|below>`: Create an alert.
- `list`: Show your alerts.
- `remove alert_id:<id>`: Delete one alert by id.
- `clear`: Delete all your alerts.
- `pause alert_id:<id>`: Pause one alert.
- `resume alert_id:<id>`: Resume one alert.
- `test symbol:<text>`: Show current price without creating an alert.

Notes:
- The alert checker runs every minute and removes triggered alerts.
- If no alert channel is set or posting fails, the bot DMs you.
