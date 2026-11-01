from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours.publish_change import publish_change, publish_changes
from db.repository import get_match
from domain import Change, Outcome, Person
from domain.names import is_command_name, parse_names, parse_swap
from domain.teams import SwapOutcome
from usecases import participation
from usecases import teams as teams_usecase
from utils.utils import (
    join_names,
    already_in_message,
    get_sender_mention,
)

SELF_ACTIONS = {
    "aggiungimi": participation.join,
    "proponimi": participation.maybe,
    "toglimi": participation.leave,
}

# the answer of each outcome, {0} is the sender
SELF_ANSWERS = {
    Outcome.ADDED: "Ok, {0}, ti aggiungo",
    Outcome.CONFIRMED: "Ok, {0}, ti confermo",
    Outcome.ALREADY_IN: "Ma {0}, sei già nella lista",
    Outcome.PROPOSED: "Ok, {0}, ti propongo",
    Outcome.MOVED_TO_MAYBE: "Ok, {0}, ti metto in forse",
    Outcome.ALREADY_MAYBE: "Ma {0}, sei già in forse",
    Outcome.REMOVED: "Mamma mia... che paccaro",
    Outcome.REMOVED_MAYBE: "Peccato, un po' ci avevo sperato",
    Outcome.NOT_IN: "Non eri in lista neanche prima",
    Outcome.NAME_TAKEN: "Ma {0}, c'è già qualcuno con questo nome nella lista",
}


def _names_by_outcome(
    names: list[str], changes: list[Change]
) -> dict[Outcome, list[str]]:
    """The names as typed (deduplicated, in order) of each outcome."""
    grouped: dict[Outcome, list[str]] = {outcome: [] for outcome in Outcome}
    for name, change in zip(dict.fromkeys(names), changes):
        grouped[change.outcome].append(name)
    return grouped


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_message = update.message.text.lower()
    # the first word must be exactly the command: "aggiungimi pure" is just chat
    command = new_message.split(" ")[0]
    chat_id = update.message.chat_id
    answer = None
    answer_is_escaped = False
    command_name_answer = "Un nome non può iniziare con /"

    is_self_action = new_message in ["aggiungimi", "toglimi", "proponimi"]
    sender = get_sender_mention(update) if is_self_action else None
    if is_self_action and sender is None:
        # the sender cannot be retrieved (issue #25): nobody to add, propose or remove
        return

    if (
        is_self_action
        or command in ["aggiungi", "togli", "proponi"]
        or command == "scambia"
    ):
        if is_self_action:
            change = SELF_ACTIONS[new_message](
                chat_id, Person(sender, update.message.from_user.id)
            )
            if change is None:
                match = None
            else:
                if change.outcome == Outcome.FULL:
                    # nothing was written: the list is as the use case saw it
                    answer = already_in_message(get_match(chat_id))
                else:
                    answer = SELF_ANSWERS[change.outcome].format(sender)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode="markdown",
                    text=escape_markdown(answer),
                )
                await publish_change(context.bot, chat_id, change)
                return
        else:
            match = get_match(chat_id)
        if match is None:
            answer = "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
            await context.bot.send_message(
                chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
            )
        else:
            target = match.target
            changes: list[Change] = []

            if command == "aggiungi":
                names = parse_names(new_message[len(command) :])
                if not names:
                    answer = "Chi dovrei aggiungere? Scrivi: aggiungi <nome>"
                elif any(is_command_name(name) for name in names):
                    answer = command_name_answer
                else:
                    changes = participation.add_names(chat_id, names) or []
                    by_outcome = _names_by_outcome(names, changes)
                    added = by_outcome[Outcome.ADDED]
                    confirmed = by_outcome[Outcome.CONFIRMED]
                    present = by_outcome[Outcome.ALREADY_IN]
                    full = by_outcome[Outcome.FULL]
                    sentences = []
                    if added:
                        sentences.append("Ok, aggiungo " + join_names(added))
                    if confirmed:
                        sentences.append(
                            "Ok, "
                            + join_names(confirmed)
                            + (
                                ", vi confermo"
                                if len(confirmed) > 1
                                else ", ti confermo"
                            )
                        )
                    if present:
                        sentences.append(
                            join_names(present)
                            + (
                                " sono già nella lista"
                                if len(present) > 1
                                else " è già nella lista"
                            )
                        )
                    if full:
                        if added or confirmed:
                            sentences.append(
                                "Ma aspetta! Non posso aggiungere "
                                + join_names(full)
                                + " perché siete già in "
                                + str(target)
                            )
                        else:
                            sentences.append(already_in_message(match))
                    answer = escape_markdown(". ".join(sentences))
                    answer_is_escaped = True

            elif command == "proponi":
                names = parse_names(new_message[len(command) :])
                if not names:
                    answer = "Chi dovrei proporre? Scrivi: proponi <nome>"
                elif any(is_command_name(name) for name in names):
                    answer = command_name_answer
                else:
                    changes = participation.propose_names(chat_id, names) or []
                    by_outcome = _names_by_outcome(names, changes)
                    proposed = by_outcome[Outcome.PROPOSED]
                    moved = by_outcome[Outcome.MOVED_TO_MAYBE]
                    present = by_outcome[Outcome.ALREADY_MAYBE]
                    full = by_outcome[Outcome.FULL]
                    sentences = []
                    if proposed:
                        sentences.append("Ok, propongo " + join_names(proposed))
                    if moved:
                        sentences.append("Va bene, metto in forse " + join_names(moved))
                    if present:
                        sentences.append(
                            join_names(present)
                            + (
                                " sono già nella lista"
                                if len(present) > 1
                                else " è già nella lista"
                            )
                        )
                    if full:
                        if proposed or moved:
                            sentences.append(
                                "Ma aspetta! Non posso proporre "
                                + join_names(full)
                                + " perché siete già in "
                                + str(target)
                            )
                        else:
                            sentences.append(already_in_message(match))
                    answer = escape_markdown(". ".join(sentences))
                    answer_is_escaped = True

            elif command == "togli":
                to_be_removed = new_message[len(command) :].strip()
                if not to_be_removed:
                    answer = "Chi dovrei togliere? Scrivi: togli <nome>"
                elif is_command_name(to_be_removed):
                    answer = command_name_answer
                else:
                    change = participation.remove_name(chat_id, to_be_removed)
                    if change is not None:
                        changes = [change]
                    if change is not None and change.outcome == Outcome.REMOVED:
                        answer = "Che vergogna, " + to_be_removed
                    elif change is not None and change.outcome == Outcome.REMOVED_MAYBE:
                        answer = (
                            "Davvero? Ma " + to_be_removed + ", ne sei proprio sicuro?"
                        )
                    else:
                        answer = (
                            to_be_removed + " non è nella lista. Chi dovrei togliere?"
                        )

            elif command == "scambia":
                names = parse_swap(new_message)
                if names is None:
                    answer = "Per scambiare due giocatori scrivi: scambia <nome 1> con <nome 2>"
                else:
                    x, y = names
                    result = teams_usecase.swap(chat_id, x, y)
                    if result is None or result.outcome == SwapOutcome.NO_TEAMS:
                        answer = "Per usare questa funzionalità devi prima formare delle squadre con /teams"
                    elif result.outcome == SwapOutcome.NOT_IN_TEAMS:
                        answer = result.missing + (
                            " non è in nessuna squadra"
                            if result.missing_is_confirmed
                            else " non c'è"
                        )
                    elif result.outcome == SwapOutcome.SAME_TEAM:
                        answer = x + " e " + y + " sono nella stessa squadra!"
                    else:
                        answer = "Perfetto, ho scambiato " + x + " con " + y

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode="markdown",
                text=answer if answer_is_escaped else escape_markdown(answer),
            )
            await publish_changes(context.bot, chat_id, changes)
