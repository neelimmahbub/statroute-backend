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
    """dev=1 activates chaos control panel in the template."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "dev_mode": bool(dev)},
    )
