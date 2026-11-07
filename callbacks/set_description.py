from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import refresh_summary
from domain.details import DetailOutcome
from usecases.details import set_description as change_description
from utils.utils import get_sender_mention


async def set_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    # the raw text after the command: context.args would collapse newlines and repeated spaces
    description = update.message.text.split(None, 1)[1:]
    description = description[0].strip() if description else ""

    result = change_description(chat_id, description)
    if result is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode="markdown",
            text="Prima di iniziare con le danze, avvia una partita, per farlo usa /start",
        )
        return

    if result.outcome == DetailOutcome.MISSING:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode="markdown",
            text="Non hai inserito la descrizione: scrivi /setdescription <descrizione>",
        )
        return

    sender = get_sender_mention(update)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=escape_markdown(f"Ok, {sender}! Ho aggiornato la descrizione!"),
    )

    await refresh_summary(context.bot, chat_id)
