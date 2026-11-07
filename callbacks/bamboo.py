from telegram import Update
from telegram.ext import ContextTypes

RETIRED_TEXT = (
    "/bamboo è andato in pensione: ora si usa /start. "
    "Se serve, il campo si cambia con /setpitch <campo>"
)


async def bamboo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retired: kept as a command only to say so. It never touches the match."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id, parse_mode="markdown", text=RETIRED_TEXT
    )
