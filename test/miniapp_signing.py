"""Helper for the tests: signs Mini App init data the way Telegram does."""

import hashlib
import hmac
import json
from urllib.parse import urlencode


def sign(fields: dict[str, str], bot_token: str) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def init_data(
    bot_token: str,
    *,
    auth_date: int,
    start_param: str = "A" * 32,
    user: dict | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    user = user or {"id": 7, "first_name": "Anna", "username": "Anna_B"}
    fields = {
        "auth_date": str(auth_date),
        "user": json.dumps(user),
        "start_param": start_param,
        **(extra or {}),
    }
    return sign(fields, bot_token)
