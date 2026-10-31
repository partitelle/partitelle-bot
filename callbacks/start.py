from telegram import Update
from telegram.ext import ContextTypes
from db.repository import get_match, create_match
from callbacks.welcome import NO_LINK_PREVIEW, WELCOME_TEXT
from domain import Match


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if get_match(chat_id) is None:
        create_match(Match.new(chat_id))

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=WELCOME_TEXT,
        link_preview_options=NO_LINK_PREVIEW,
    )
