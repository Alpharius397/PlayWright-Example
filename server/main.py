""" Server Entry Point """
import random
from typing import Any
from asyncio import sleep
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader, select_autoescape, Template
from utils import CaseType, WebScraper
from server.log import logger

env = Environment(loader=PackageLoader("server"), autoescape=select_autoescape())

indexTemplate: Template = env.get_template(name="index.html")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

WEBSCRAPER = WebScraper("static")


class ConnectionManager:
    """Websocket Connection Manager"""

    AUTH: str = "id"

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Websocket Connect"""
        try:
            assert (
                ConnectionManager.AUTH in websocket.cookies
            ), "Auth cookie was not found"
            await websocket.accept()

            idx = websocket.cookies[ConnectionManager.AUTH]
            self.active_connections.update({idx: websocket})
            logger.info("WebSocket connected")

        except (RuntimeError, AssertionError) as e:
            logger.error("Error connecting WebSocket: %s", e, exc_info=True)

    async def disconnect(self, websocket: WebSocket):
        """Websocket disconnect"""

        try:
            assert (
                ConnectionManager.AUTH in websocket.cookies
            ), "Auth cookie was not found"

            idx = websocket.cookies[ConnectionManager.AUTH]
            self.active_connections.pop(idx)

            await websocket.close()
            logger.info("WebSocket disconnected")

        except (RuntimeError, AssertionError) as e:
            logger.error("Error disconnecting WebSocket: %s", e, exc_info=True)

    async def broadcast(self, idx: str, message: dict[str, Any]):
        """Websocket Broadcast"""

        try:
            if idx in self.active_connections:
                socket = self.active_connections[idx]
                await socket.send_json(message)
                logger.info("Broadcast message sent")
        except (RuntimeError, AssertionError) as e:
            logger.error("Error Broadcasting: %s", e, exc_info=True)


manager = ConnectionManager()


@app.get("/")
async def index():
    """Homepage render"""
    resp = HTMLResponse(indexTemplate.render())
    resp.set_cookie(
        ConnectionManager.AUTH,
        str(random.randint(1, 10000000)),
        httponly=True,
        samesite="strict",
    )
    return resp


@app.post("/api/court/all")
async def get_all_court_pdf(req: Request):
    """
    Retrieve pdfs for given court name only
    """

    idx = req.cookies[ConnectionManager.AUTH]

    try:
        assert ConnectionManager.AUTH in req.cookies, "Auth cookie was not found"
        data = await req.form(max_files=0)
        chosen_state: str = str(data["chosen_state"])

        assert isinstance(chosen_state, str), "Chosen State must be a string"

        chosen_dist: str = str(data["chosen_dist"])

        assert isinstance(chosen_dist, str), "Chosen District must be a string"

        chosen_court: str = str(data["chosen_court"])

        assert isinstance(chosen_court, str), "Chosen Court Name must be a string"

        chosen_date: str = str(data["chosen_date"])

        assert isinstance(chosen_date, str), "Chosen Date must be a string"

        assert isinstance(data["case_type"], str) and (
            data["case_type"] in ["Civil", "Criminal"]
        ), "Chosen State must be a string"

        case_type: CaseType = (
            CaseType.CRIMINAL
            if (str(data["case_type"]) == "Criminal")
            else CaseType.CIVIL
        )

        async for cnr, path in WEBSCRAPER.begin_scrape_all(
            chosen_state, chosen_dist, chosen_court, chosen_date, case_type
        ):
            await manager.broadcast(idx, {"cnr": cnr, "path": path})

    except (AssertionError, RuntimeError):
        logger.error("[ERROR]: Multiple Court PDF generation failed", exc_info=True)
        await manager.broadcast(idx, {"error": "Request Failed. Please try again"})


@app.post("/api/court")
async def get_court_pdf(req: Request):
    """
    Retrieve pdfs for given court name only
    """

    idx = req.cookies[ConnectionManager.AUTH]
    try:
        assert ConnectionManager.AUTH in req.cookies, "Auth cookie was not found"
        data = await req.form(max_files=0)
        chosen_state: str = str(data["chosen_state"])

        assert isinstance(chosen_state, str), "Chosen State must be a string"

        chosen_dist: str = str(data["chosen_dist"])

        assert isinstance(chosen_dist, str), "Chosen District must be a string"

        chosen_court: str = str(data["chosen_court"])

        assert isinstance(chosen_court, str), "Chosen Court Name must be a string"

        chosen_date: str = str(data["chosen_date"])

        assert isinstance(chosen_date, str), "Chosen Date must be a string"

        chosen_court_name: str = str(data["chosen_court_name"])

        assert isinstance(chosen_court_name, str), "Chosen Date must be a string"

        assert isinstance(data["case_type"], str) and (
            data["case_type"] in ["Civil", "Criminal"]
        ), "Chosen State must be a string"

        case_type: CaseType = (
            CaseType.CRIMINAL
            if (str(data["case_type"]) == "Criminal")
            else CaseType.CIVIL
        )

        async for cnr, path in WEBSCRAPER.begin_scrape(
            chosen_state,
            chosen_dist,
            chosen_court,
            chosen_court_name,
            chosen_date,
            case_type,
        ):
            await manager.broadcast(idx, {"cnr": cnr, "path": path})

    except (AssertionError, RuntimeError):
        logger.error("[ERROR]: Single Court PDF generation failed", exc_info=True)

        await manager.broadcast(idx, {"error": "Request Failed. Please try again"})


@app.websocket("/pdf")
async def websocket_predict(websocket: WebSocket):
    """Websocket connection for updating pdf links"""
    try:
        await manager.connect(websocket)
        while True:
            await sleep(5)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("WebSocket disconnected normally")
    except (RuntimeError, AssertionError) as e:
        await manager.disconnect(websocket)
        logger.error("WebSocket error: %s", e, exc_info=True)
