from telegram import Update
from telegram.ext import ContextTypes
from behaviours import replies
from usecases.teams import make_teams


async def teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = make_teams(chat_id)
    answer = replies.NO_MATCH_ANSWER if result is None else replies.teams_reply(result)

    await context.bot.send_message(
        chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
    )
