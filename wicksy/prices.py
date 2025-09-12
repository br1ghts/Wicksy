import re
import requests
import yfinance as yf


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
