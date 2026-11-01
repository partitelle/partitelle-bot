"""The Mini App's routes: its page, its static files and the JSON API behind it.

The API trusts nothing from the client except the init data Telegram signed (see web/init_data.py).
Its token (the `start_param`) selects the match, and the user must be a member of the match's chat.
Nothing sensitive is logged: when something fails only the exception type is.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application

from behaviours.publish_change import publish_change
from db.repository import find_chat_by_miniapp_token, get_match
from domain import Change, Match, Person, display_name
from domain.schedule import format_day, format_time
from usecases import participation
from web.init_data import InitData, InvalidInitData, validate_init_data
from web.membership import CachedMembership
from web.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

AUTH_SCHEME = "tma"
MAX_BODY = 1024  # bytes
ACTIONS: dict[str, Callable[[int, Person], Change | None]] = {
    "join": participation.join,
    "maybe": participation.maybe,
    "leave": participation.leave,
}
API_PER_MINUTE = 600  # all API requests together, checked before any HMAC work
USER_PER_MINUTE = 60
ACTIONS_PER_MINUTE = 10

MINIAPP_DIR = Path(__file__).resolve().parent / "miniapp"
INDEX = MINIAPP_DIR / "index.html"
STATIC_DIR = MINIAPP_DIR / "static"

PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache",
}
API_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _Static(StaticFiles):
    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def _error(status_code: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status_code, headers=API_HEADERS)


class _Stop(Exception):
    """Carries the error response of a failed check."""

    def __init__(self, response: Response) -> None:
        self.response = response


def _state(match: Match, person: Person) -> dict[str, Any]:
    found = match.find_person(person)
    status = "out" if found is None else "maybe" if found.is_maybe else "in"
    return {
        "match": {
            "day": format_day(match.starts),
            "time": format_time(match.starts),
            "target": match.target,
            "has_room": match.has_room,
            "pitch": match.pitch,
            "confirmed": match.confirmed_names(),
            "maybe": [p.name for p in match.participants if p.is_maybe],
            "teams": None if match.teams is None else match.teams.as_dict(),
        },
        "me": {"name": person.name, "status": status},
    }


async def _read_json(request: Request) -> Any:
    """The JSON body, at most MAX_BODY bytes; raises ValueError otherwise."""
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise ValueError("body too large")
        chunks.append(chunk)
    return json.loads(b"".join(chunks))


def miniapp_routes(
    application: Application,  # type: ignore[type-arg]
    bot_token: str,
    *,
    max_age: int = 3600,
    now: Clock = _utc_now,
    api_limiter: RateLimiter | None = None,
    user_limiter: RateLimiter | None = None,
    action_limiter: RateLimiter | None = None,
    membership: CachedMembership | None = None,
) -> Sequence[BaseRoute]:
    """The routes of the Mini App. Only add them when the feature is on."""
    # `is None`, not `or`: an empty limiter or cache is falsy (it has a length)
    if api_limiter is None:
        api_limiter = RateLimiter(API_PER_MINUTE)
    if user_limiter is None:
        user_limiter = RateLimiter(USER_PER_MINUTE)
    if action_limiter is None:
        action_limiter = RateLimiter(ACTIONS_PER_MINUTE)
    if membership is None:
        membership = CachedMembership()

    async def page(request: Request) -> Response:
        return FileResponse(INDEX, headers=PAGE_HEADERS)

    async def authenticate(request: Request) -> tuple[InitData, Person]:
        if not api_limiter.allow():
            raise _Stop(_error(429, "rate_limited"))
        scheme, _, raw = request.headers.get("Authorization", "").partition(" ")
        try:
            if scheme != AUTH_SCHEME:
                raise InvalidInitData("no credentials")
            data = validate_init_data(raw, bot_token, now=now(), max_age=max_age)
        except InvalidInitData:
            raise _Stop(_error(401, "session")) from None
        name = display_name(data.username, data.first_name, data.last_name)
        if name is None:
            raise _Stop(_error(401, "session"))
        if not user_limiter.allow(data.user_id):
            raise _Stop(_error(429, "rate_limited"))
        return data, Person(name, data.user_id)

    async def authorize(data: InitData) -> int:
        """The chat of the match the user opened, once they are known to belong to it."""
        chat_id = await asyncio.to_thread(find_chat_by_miniapp_token, data.start_param)
        if chat_id is None:
            raise _Stop(_error(404, "match_closed"))
        if not await membership.check(application.bot, chat_id, data.user_id):
            raise _Stop(_error(403, "not_member"))
        return chat_id

    async def read_state(chat_id: int, person: Person) -> dict[str, Any]:
        match = await asyncio.to_thread(get_match, chat_id)
        if match is None:
            raise _Stop(_error(404, "match_closed"))
        return _state(match, person)

    async def handle(
        request: Request,
        body_ok: Callable[[Any], bool],
        run: Callable[[Request, int, Person, Any], Any],
    ) -> Response:
        try:
            data, person = await authenticate(request)
            try:
                body = await _read_json(request)
            except ValueError:  # includes bad JSON and bad UTF-8
                return _error(400, "bad_request")
            if not body_ok(body):
                return _error(400, "bad_request")
            chat_id = await authorize(data)
            return JSONResponse(
                await run(request, chat_id, person, body), headers=API_HEADERS
            )
        except _Stop as stop:
            return stop.response
        except (TimedOut, NetworkError) as error:
            logger.warning("Mini app: Telegram unavailable: %s", type(error).__name__)
            return _error(503, "unavailable")
        except Exception as error:
            # never the error text: it could hold names, ids or the token
            logger.warning("Mini app: request failed: %s", type(error).__name__)
            return _error(503, "unavailable")

    async def run_match(
        request: Request, chat_id: int, person: Person, body: Any
    ) -> dict[str, Any]:
        return await read_state(chat_id, person)

    async def run_action(
        request: Request, chat_id: int, person: Person, body: Any
    ) -> Any:
        if not action_limiter.allow(person.telegram_user_id):
            raise _Stop(_error(429, "rate_limited"))
        try:
            change = await asyncio.to_thread(ACTIONS[body["action"]], chat_id, person)
        except ValueError:  # lost a race with another writer
            raise _Stop(_error(409, "conflict")) from None
        except LookupError:  # the match was stopped in the meantime
            raise _Stop(_error(404, "match_closed")) from None
        if change is None:
            raise _Stop(_error(404, "match_closed"))
        try:
            await publish_change(application.bot, chat_id, change)
        except Exception as error:
            logger.warning(
                "Mini app: could not update the group: %s", type(error).__name__
            )
        return {
            "outcome": change.outcome.value,
            "teams_cancelled": change.revokes_teams,
            "state": await read_state(chat_id, person),
        }

    async def api_match(request: Request) -> Response:
        return await handle(request, lambda body: body == {}, run_match)

    async def api_action(request: Request) -> Response:
        def valid(body: Any) -> bool:
            return (
                isinstance(body, dict)
                and set(body) == {"action"}
                and isinstance(body["action"], str)
                and body["action"] in ACTIONS
            )

        return await handle(request, valid, run_action)

    return [
        Route("/app", page, methods=["GET"]),
        Mount("/app/static", _Static(directory=STATIC_DIR)),
        Route("/app/api/match", api_match, methods=["POST"]),
        Route("/app/api/action", api_action, methods=["POST"]),
    ]
