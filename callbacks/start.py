from telegram import Update
from telegram.ext import ContextTypes
from callbacks.welcome import NO_LINK_PREVIEW, WELCOME_TEXT
from usecases.lifecycle import start_match


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_match(update.message.chat_id)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=WELCOME_TEXT,
        link_preview_options=NO_LINK_PREVIEW,
    )
