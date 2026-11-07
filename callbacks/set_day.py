from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import refresh_summary
from domain.details import DetailOutcome
from domain.schedule import format_day
from usecases.details import set_day as change_day
from utils.utils import flatten_args, get_sender_mention


async def set_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = change_day(chat_id, flatten_args(context.args))
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
            text="Non hai inserito il giorno: scrivi /setday <giorno>",
        )
        return

    sender = get_sender_mention(update)
    if result.outcome == DetailOutcome.UNREADABLE:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode="markdown",
            text=escape_markdown(
                f"Non ho capito il giorno, {sender}: "
                "scrivilo come GG/MM/AAAA, per esempio /setday 25/10/2026"
            ),
        )
        return

    starts = result.starts
    assert starts is not None
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=escape_markdown(
            f"Ok, {sender}! Ho impostato il giorno della partita: {format_day(starts).lower()}"
        ),
    )

    await refresh_summary(context.bot, chat_id)
