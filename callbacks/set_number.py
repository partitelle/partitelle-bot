from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import publish_target_change
from db.repository import get_match
from domain import TargetTooLow
from domain.target import TargetOutcome
from usecases.target import change_target
from utils.utils import get_sender_mention


def target_too_low_answer(refusal: TargetTooLow, current_target: int) -> str:
    advice = (
        "Prima togli qualcuno con togli <nome>, oppure lascia il numero a "
        f"{current_target} 🙏"
    )
    if refusal.maybe == 0:
        return (
            f"Non posso scendere a {refusal.requested}: "
            f"ci sono già {refusal.confirmed} confermati. {advice}"
        )
    maybes = f"{refusal.maybe} in forse"
    if refusal.confirmed == 0:
        counts = maybes
    elif refusal.confirmed == 1:
        counts = f"1 confermato e {maybes}"
    else:
        counts = f"{refusal.confirmed} confermati e {maybes}"
    return (
        f"Non posso scendere a {refusal.requested}: "
        f"in lista ci sono già {refusal.total} persone ({counts}), "
        f"e anche chi è in forse tiene un posto. {advice}"
    )


async def set_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    match = get_match(chat_id)

    if match is None:
        answer = (
            "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
        )
    else:
        try:
            if len(context.args) > 1:
                answer = (
                    "Hai messo più di un numero, probabilmente intendevi /setnumber "
                    + context.args[0]
                )
            else:
                chosen_number_str = context.args[0]
                sender = get_sender_mention(update)

                if chosen_number_str.isnumeric():
                    chosen_number = int(chosen_number_str)
                    result = change_target(chat_id, chosen_number)
                    if result is None:
                        # stopped between the two reads: nothing to change
                        raise LookupError("the match was stopped")
                    if result.outcome == TargetOutcome.INVALID:
                        answer = "Non è un numero valido di partecipanti 🌚"
                    elif result.outcome == TargetOutcome.TOO_SMALL:
                        answer = "Il numero che hai inserito non va bene 👎"
                    elif result.outcome == TargetOutcome.TOO_LOW:
                        answer = target_too_low_answer(
                            result.refusal, result.previous_target
                        )
                    else:
                        answer = (
                            "Ok, "
                            + sender
                            + "! Ho impostato il numero di partecipanti a "
                            + str(chosen_number)
                        )
                        await publish_target_change(context.bot, chat_id, result)
                else:
                    answer = sender + ", quello ti sembra un numero? 😂"

        except Exception:
            answer = "Non hai inserito il numero: scrivi /setnumber <numero>"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        parse_mode="markdown",
        text=escape_markdown(answer),
    )
