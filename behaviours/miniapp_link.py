"""The "apri la lista" button under the match summary: a link that opens the Mini App on that match."""

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from conf import conf
from db.repository import get_or_create_miniapp_token

BUTTON_TEXT = "apri la lista"


def miniapp_url(bot_username: str, short_name: str, token: str) -> str:
    """The direct link of a Mini App: it opens the app with `token` as its start parameter."""
    return f"https://t.me/{bot_username}/{short_name}?startapp={token}"


def miniapp_markup(bot: Bot, chat_id: int) -> InlineKeyboardMarkup | None:
    """The one-button keyboard of the summary of a chat, or None when the Mini App is off or the
    chat has no active match (an edit without markup removes the button)."""
    short_name = conf.miniapp_short_name
    if not short_name:
        return None
    token = get_or_create_miniapp_token(chat_id)
    username = conf.bot_username or bot.username
    if token is None or not username:
        return None
    button = InlineKeyboardButton(
        BUTTON_TEXT, url=miniapp_url(username, short_name, token)
    )
    return InlineKeyboardMarkup([[button]])
