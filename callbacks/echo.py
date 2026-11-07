from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from behaviours import replies
from behaviours.publish_change import publish_change, publish_changes
from db.repository import get_match
from domain import Change, Person
from domain.names import is_command_name, parse_names, parse_swap
from usecases import participation
from usecases import teams as teams_usecase
from utils.utils import get_sender_mention

SELF_ACTIONS = {
    "aggiungimi": participation.join,
    "proponimi": participation.maybe,
    "toglimi": participation.leave,
}


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
                # on FULL nothing was written: the list is as the use case saw it
                answer = replies.self_reply(change, sender, get_match(chat_id))
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    parse_mode="markdown",
                    text=answer,
                )
                await publish_change(context.bot, chat_id, change)
                return
        else:
            match = get_match(chat_id)
        if match is None:
            answer = replies.NO_MATCH_ANSWER
            await context.bot.send_message(
                chat_id=update.effective_chat.id, parse_mode="markdown", text=answer
            )
        else:
            changes: list[Change] = []

            if command == "aggiungi":
                names = parse_names(new_message[len(command) :])
                if not names:
                    answer = "Chi dovrei aggiungere? Scrivi: aggiungi <nome>"
                elif any(is_command_name(name) for name in names):
                    answer = command_name_answer
                else:
                    changes = participation.add_names(chat_id, names) or []
                    answer = replies.add_reply(names, changes, match)
                    answer_is_escaped = True

            elif command == "proponi":
                names = parse_names(new_message[len(command) :])
                if not names:
                    answer = "Chi dovrei proporre? Scrivi: proponi <nome>"
                elif any(is_command_name(name) for name in names):
                    answer = command_name_answer
                else:
                    changes = participation.propose_names(chat_id, names) or []
                    answer = replies.propose_reply(names, changes, match)
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
                    answer = replies.remove_reply(to_be_removed, change)
                    answer_is_escaped = True

            elif command == "scambia":
                names = parse_swap(new_message)
                if names is None:
                    answer = "Per scambiare due giocatori scrivi: scambia <nome 1> con <nome 2>"
                else:
                    x, y = names
                    answer = replies.swap_reply(teams_usecase.swap(chat_id, x, y))
                    answer_is_escaped = True

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                parse_mode="markdown",
                text=answer if answer_is_escaped else escape_markdown(answer),
            )
            await publish_changes(context.bot, chat_id, changes)
