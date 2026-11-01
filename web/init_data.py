"""Validation of the data Telegram hands to a Mini App (`Telegram.WebApp.initData`).

Pure: no I/O, no logging. Algorithm: https://core.telegram.org/bots/webapps
("Validating data received via the Mini App"). Only the few fields the app needs survive.
"""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl

MAX_LENGTH = 4096
FUTURE_TOLERANCE = 60  # seconds an auth_date may be ahead of our clock
_HASH = re.compile(r"[0-9a-f]{64}")
_START_PARAM = re.compile(r"[A-Za-z0-9_-]{16,64}")


class InvalidInitData(Exception):
    """The init data is malformed, forged, or expired. The message never holds the data."""


@dataclass(frozen=True)
class InitData:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    start_param: str


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def validate_init_data(
    raw: str, bot_token: str, *, now: datetime, max_age: int
) -> InitData:
    if len(raw) > MAX_LENGTH:
        raise InvalidInitData("too long")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InvalidInitData("not a query string") from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InvalidInitData("duplicate key")
    received = fields.pop("hash", "")
    if not _HASH.fullmatch(received):
        raise InvalidInitData("bad hash")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InvalidInitData("signature mismatch")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError):
        raise InvalidInitData("bad auth_date") from None
    age = now.timestamp() - auth_date
    if age > max_age or age < -FUTURE_TOLERANCE:
        raise InvalidInitData("expired")

    try:
        user = json.loads(fields["user"])
    except (KeyError, ValueError):
        raise InvalidInitData("bad user") from None
    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise InvalidInitData("bad user")

    start_param = fields.get("start_param", "")
    if not _START_PARAM.fullmatch(start_param):
        raise InvalidInitData("bad start_param")
    return InitData(
        user_id=user_id,
        username=_text(user.get("username")),
        first_name=_text(user.get("first_name")),
        last_name=_text(user.get("last_name")),
        start_param=start_param,
    )
