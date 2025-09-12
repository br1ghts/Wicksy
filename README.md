# Wicksy

Wicksy is a Discord bot that helps you track crypto and stock prices in real time.
It manages a shared watchlist with auto-updating tables, alerts, and trade logging — designed for traders who want live insights directly in their Discord server.

---

## ✨ Features

- `/watchlist add` — add crypto (via CoinGecko) or stock tickers (via Yahoo Finance).
- `/watchlist list` — display your live watchlist in a clean table.
- `/watchlist remove` — remove a symbol from the watchlist.
- `/watchlist clear` — reset the watchlist.
- Auto-updates every minute with fresh data.
- Supports both **stocks** and **crypto**.

---

## 🚀 Installation

### 1. Clone the repo

```bash
git clone https://github.com/br1ghts/Wicksy.git
cd Wicksy
```

### 2. Set up virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux / macOS
venv\Scripts\activate     # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

Create a `.env` file in the project root:

```
DISCORD_TOKEN=your_discord_bot_token
```

### 5. Run Wicksy

```bash
python3 bot.py
```

---

## ⚙️ Configuration

- Wicksy uses SQLite (`Wicksy.db`) for persistence.
- Watchlist channel/message IDs are stored automatically.
- CoinGecko API powers crypto prices.
- Yahoo Finance powers stock data.

---

## 🛠 Development

Want to contribute?

- Fork the repo
- Create a feature branch
- Submit a pull request

---

## 📜 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
