from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "dev_mode": settings.dev_mode,
        },
    )
import pathlib
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(
    directory=str(pathlib.Path(__file__).parent / "templates")
)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, dev: int = 0) -> HTMLResponse:
    """
    Args: dev=1 activates chaos control panel in the template.
    Returns: Jinja2 rendered dashboard page.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "dev_mode": bool(dev)},
    )
