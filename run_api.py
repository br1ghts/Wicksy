from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from wicksy.features import get_watchlist, get_alerts, get_trades
from wicksy.web.dashboard import router as dashboard_router

app = FastAPI()

# Mount static files for the dashboard
static_dir = Path(__file__).parent / "wicksy" / "web" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(dashboard_router)


@app.get("/watchlist")
async def watchlist_endpoint():
    return await get_watchlist()


@app.get("/alerts")
async def alerts_endpoint():
    return await get_alerts()


@app.get("/trades")
async def trades_endpoint():
    return await get_trades()
