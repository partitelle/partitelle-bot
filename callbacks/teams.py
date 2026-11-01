from telegram import Update
from telegram.ext import ContextTypes
from domain.teams import TeamsOutcome
from usecases.teams import make_teams
from utils.utils import format_teams


async def teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = make_teams(chat_id)

    if result is None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            parse_mode="markdown",
            text="Prima di iniziare con le danze, avvia una partita, per farlo usa /start",
        )
        return

    if result.outcome == TeamsOutcome.ODD_TARGET:
        answer = "Per usare questa funzionalità dovete essere in un numero pari di partecipanti"
    elif result.outcome == TeamsOutcome.NOT_FULL:
        answer = f"Prima di poter fare le squadre, devi raggiungere {result.target} partecipanti"
    else:
        answer = format_teams(result.teams)

    await context.bot.send_message(
        chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
    )
