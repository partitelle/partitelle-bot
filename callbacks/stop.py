from telegram import Update
from telegram.ext import ContextTypes
from usecases.lifecycle import stop_match


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if not stop_match(chat_id):
        answer = (
            "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
        )
    else:
        answer = "Ho chiuso la partita. Per organizzarne una nuova usa /start"
    await context.bot.send_message(
        chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
    )
