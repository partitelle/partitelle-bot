"""The bot's web app: Telegram webhook and health check (more routes, e.g. jobs, can be added here)."""

import asyncio
import hmac
import logging
import os
from collections.abc import Awaitable, Callable, Mapping

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application

from db.connection import ping

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "telegram"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
HEALTH_CORS_ORIGIN = "https://partitelle.com"
HEALTH_TIMEOUT = 5  # seconds, for the whole database check

DatabaseCheck = Callable[[], Awaitable[None]]


def resolve_version(environ: Mapping[str, str] = os.environ) -> str:
    """`PB_VERSION`, else the short commit Render deployed, else "unknown"."""
    if environ.get("PB_VERSION"):
        return environ["PB_VERSION"]
    if environ.get("RENDER_GIT_COMMIT"):
        return environ["RENDER_GIT_COMMIT"][:7]
    return "unknown"


async def check_database() -> None:
    """Raise when the database does not answer a ping within HEALTH_TIMEOUT."""
    await asyncio.wait_for(
        asyncio.to_thread(ping, HEALTH_TIMEOUT), timeout=HEALTH_TIMEOUT
    )


def create_app(
    application: Application,  # type: ignore[type-arg]
    secret: str,
    check: DatabaseCheck = check_database,
    version: str | None = None,
) -> Starlette:
    """Build the web app. `application` receives the updates, `secret` guards the webhook."""

    async def telegram(request: Request) -> Response:
        received = request.headers.get(SECRET_HEADER, "")
        if not hmac.compare_digest(received.encode(), secret.encode()):
            return Response(status_code=403)
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
        except (ValueError, TypeError, AttributeError):
            update = None
        if update is None:
            return Response(status_code=400)
        await application.update_queue.put(update)
        return Response(status_code=200)

    async def health(request: Request) -> Response:
        try:
            await check()
            database, status_code, status = "ok", 200, "ok"
        except Exception:
            # the body never carries the error text; the log has the type only
            logger.warning("Health check: the database is unavailable")
            database, status_code, status = "unavailable", 503, "degraded"
        body = {
            "status": status,
            "version": version or resolve_version(),
            "database": database,
        }
        headers = {"Cache-Control": "no-store"}
        if request.headers.get("origin") == HEALTH_CORS_ORIGIN:
            headers["Access-Control-Allow-Origin"] = HEALTH_CORS_ORIGIN
            headers["Access-Control-Allow-Methods"] = "GET"
            headers["Vary"] = "Origin"
        return JSONResponse(body, status_code=status_code, headers=headers)

    return Starlette(
        routes=[
            Route(f"/{WEBHOOK_PATH}", telegram, methods=["POST"]),
            Route("/health", health, methods=["GET"]),  # HEAD is added by Starlette
        ]
    )
