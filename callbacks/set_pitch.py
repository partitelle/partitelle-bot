from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import refresh_summary
from domain.details import DetailOutcome
from usecases.details import set_pitch as change_pitch
from utils.utils import flatten_args, get_sender_mention


async def set_pitch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = change_pitch(chat_id, flatten_args(context.args))
    if result is None:
        answer = (
            "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
        )
    else:
        if result.outcome == DetailOutcome.MISSING:
            answer = "Non hai inserito il campo: scrivi /setpitch <campo>"
            await context.bot.send_message(
                chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
            )
        else:
            sender = get_sender_mention(update)
            answer = "Ok, " + sender + "! Ho aggiornato il campo!"
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode="markdown",
                text=escape_markdown(answer),
            )
            await refresh_summary(context.bot, chat_id)
