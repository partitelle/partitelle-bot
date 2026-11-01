"""The bot's web app: Telegram webhook and health check (more routes, e.g. jobs, can be added here)."""

import asyncio
import hmac
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application

from behaviours.send_due_reminders import send_due_reminders
from db.connection import ping

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "telegram"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
HEALTH_CORS_ORIGIN = "https://partitelle.com"
HEALTH_TIMEOUT = 5  # seconds, for the whole database check

DatabaseCheck = Callable[[], Awaitable[None]]
ReminderSender = Callable[[Any, datetime], Awaitable[dict[str, int]]]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    jobs_secret: str | None = None,
    send_reminders: ReminderSender = send_due_reminders,
    now: Clock = utc_now,
) -> Starlette:
    """Build the web app. `application` receives the updates, `secret` guards the webhook.

    `jobs_secret` guards the jobs endpoints; when unset or empty they are disabled (404).
    """

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

    async def payment_reminders(request: Request) -> Response:
        if not jobs_secret:
            return Response(status_code=404)
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme != "Bearer" or not hmac.compare_digest(
            token.encode(), jobs_secret.encode()
        ):
            return Response(status_code=401)
        try:
            counts = await send_reminders(application.bot, now())
        except Exception as error:
            # the body and the log never carry the error text: it could hold chat ids or names
            logger.warning("Payment reminders job failed: %s", type(error).__name__)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse(
            {key: counts[key] for key in ("sent", "skipped", "failed")},
            headers={"Cache-Control": "no-store"},
        )

    return Starlette(
        routes=[
            Route(f"/{WEBHOOK_PATH}", telegram, methods=["POST"]),
            Route("/health", health, methods=["GET"]),  # HEAD is added by Starlette
            Route("/jobs/payment-reminders", payment_reminders, methods=["POST"]),
        ]
    )
