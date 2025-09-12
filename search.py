import requests


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
    query = query.strip()
    if not query:
        return []  # 🔥 avoid hitting Yahoo with empty query

    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params={"q": query}, headers=headers, timeout=5)

        if resp.status_code != 200:
            print(f"⚠️ Stock search failed: HTTP {resp.status_code} for query='{query}'")
            return []

        results = resp.json().get("quotes", [])
        return [
            {"symbol": q["symbol"], "name": q.get("shortname", q["symbol"])}
            for q in results
            if "symbol" in q
        ]
    except Exception as e:
        print(f"⚠️ Stock search failed: {e}")
        return []
