from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import refresh_summary
from domain.details import DetailOutcome
from domain.schedule import format_time
from usecases.details import set_time as change_time
from utils.utils import flatten_args, get_sender_mention


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = change_time(chat_id, flatten_args(context.args))
    if result is None:
        answer = (
            "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
        )
        return

    if result.outcome == DetailOutcome.MISSING:
        answer = "Non hai inserito l'orario: scrivi /settime <orario>"
        await context.bot.send_message(
            chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
        )
        return

    sender = get_sender_mention(update)
    if result.outcome == DetailOutcome.UNREADABLE:
        answer = (
            f"Non ho capito l'ora, {sender}: "
            "scrivila come HH:MM, per esempio /settime 21:30"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode="markdown",
            text=escape_markdown(answer),
        )
        return

    starts = result.starts
    assert starts is not None
    answer = (
        "Ok, "
        + sender
        + "! Ho impostato l'orario della partita alle "
        + format_time(starts)
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=escape_markdown(answer),
    )
    await refresh_summary(context.bot, chat_id)
