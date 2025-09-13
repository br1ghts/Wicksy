from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from wicksy.features import get_watchlist, get_alerts, get_trades

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    watchlist = await get_watchlist()
    alerts = await get_alerts()
    trades = await get_trades()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "watchlist": watchlist,
            "alerts": alerts,
            "trades": trades,
        },
    )
