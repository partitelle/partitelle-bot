"""What the bot answers in the group to each action on the list, as the final Telegram
markdown text (already escaped where it must be).

The chat handlers and the Mini App API both build their answers here, so a group sees the
same words whichever way the action came in.
"""

from collections.abc import Sequence

from telegram.helpers import escape_markdown

from domain import Change, Match, Outcome
from domain.teams import SwapOutcome, SwapResult, TeamsOutcome, TeamsResult
from utils.utils import already_in_message, format_teams, join_names

NO_MATCH_ANSWER = (
    "Prima di iniziare con le danze, avvia una partita, per farlo usa /start"
)

# the answer of each outcome of a self action, {0} is the sender
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
    names: Sequence[str], changes: Sequence[Change]
) -> dict[Outcome, list[str]]:
    """The names as typed (deduplicated, in order) of each outcome."""
    grouped: dict[Outcome, list[str]] = {outcome: [] for outcome in Outcome}
    for name, change in zip(dict.fromkeys(names), changes):
        grouped[change.outcome].append(name)
    return grouped


def self_reply(change: Change, sender: str, match: Match) -> str:
    """The answer to aggiungimi, proponimi, toglimi. `match` is the list after the change
    (it only matters for FULL, where nothing was written)."""
    if change.outcome == Outcome.FULL:
        answer = already_in_message(match)
    else:
        answer = SELF_ANSWERS[change.outcome].format(sender)
    return escape_markdown(answer)


def _is_already_in_the_list(present: list[str]) -> str:
    return join_names(present) + (
        " sono già nella lista" if len(present) > 1 else " è già nella lista"
    )


def add_reply(names: Sequence[str], changes: Sequence[Change], match: Match) -> str:
    """The answer to "aggiungi <names>". `match` is the list before the command."""
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
            + (", vi confermo" if len(confirmed) > 1 else ", ti confermo")
        )
    if present:
        sentences.append(_is_already_in_the_list(present))
    if full:
        if added or confirmed:
            sentences.append(
                "Ma aspetta! Non posso aggiungere "
                + join_names(full)
                + " perché siete già in "
                + str(match.target)
            )
        else:
            sentences.append(already_in_message(match))
    return escape_markdown(". ".join(sentences))


def propose_reply(names: Sequence[str], changes: Sequence[Change], match: Match) -> str:
    """The answer to "proponi <names>". `match` is the list before the command."""
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
        sentences.append(_is_already_in_the_list(present))
    if full:
        if proposed or moved:
            sentences.append(
                "Ma aspetta! Non posso proporre "
                + join_names(full)
                + " perché siete già in "
                + str(match.target)
            )
        else:
            sentences.append(already_in_message(match))
    return escape_markdown(". ".join(sentences))


def remove_reply(name: str, change: Change | None) -> str:
    """The answer to "togli <name>"."""
    if change is not None and change.outcome == Outcome.REMOVED:
        answer = "Che vergogna, " + name
    elif change is not None and change.outcome == Outcome.REMOVED_MAYBE:
        answer = "Davvero? Ma " + name + ", ne sei proprio sicuro?"
    else:
        answer = name + " non è nella lista. Chi dovrei togliere?"
    return escape_markdown(answer)


def swap_reply(result: SwapResult | None) -> str:
    """The answer to "scambia <x> con <y>"."""
    if result is None or result.outcome == SwapOutcome.NO_TEAMS:
        answer = (
            "Per usare questa funzionalità devi prima formare delle squadre con /teams"
        )
    elif result.outcome == SwapOutcome.NOT_IN_TEAMS:
        assert result.missing is not None
        answer = result.missing + (
            " non è in nessuna squadra" if result.missing_is_confirmed else " non c'è"
        )
    elif result.outcome == SwapOutcome.SAME_TEAM:
        answer = result.x + " e " + result.y + " sono nella stessa squadra!"
    else:
        answer = "Perfetto, ho scambiato " + result.x + " con " + result.y
    return escape_markdown(answer)


def teams_reply(result: TeamsResult) -> str:
    """The answer to /teams (the teams message is built as it has always been)."""
    if result.outcome == TeamsOutcome.ODD_TARGET:
        return "Per usare questa funzionalità dovete essere in un numero pari di partecipanti"
    if result.outcome == TeamsOutcome.NOT_FULL:
        return f"Prima di poter fare le squadre, devi raggiungere {result.target} partecipanti"
    assert result.teams is not None
    return format_teams(result.teams)


# Who acted on others from the Mini App (plain text, sent before the reply). PROVISIONAL copy.
ACTOR_ADDED = "{actor} ha aggiunto {names}"
ACTOR_CONFIRMED = "{actor} ha confermato {names}"
ACTOR_PROPOSED = "{actor} ha messo in forse {names}"
ACTOR_MOVED_TO_MAYBE = "{actor} ha spostato in forse {names}"
ACTOR_REMOVED = "{actor} ha tolto {name}"
ACTOR_SWAPPED = "{actor} ha scambiato {x} con {y}"

_ACTOR_TEMPLATES = (
    (Outcome.ADDED, ACTOR_ADDED),
    (Outcome.CONFIRMED, ACTOR_CONFIRMED),
    (Outcome.PROPOSED, ACTOR_PROPOSED),
    (Outcome.MOVED_TO_MAYBE, ACTOR_MOVED_TO_MAYBE),
)


def actor_line(
    actor: str,
    changes: Sequence[Change] | None = None,
    swap: SwapResult | None = None,
) -> str | None:
    """Who acted on other people, as plain text (no markdown, nothing to escape), or None
    when there is nothing to attribute. Only effective changes count, and a target with the
    actor's own name (case-insensitive) is the actor acting on themselves."""

    def others(names: Sequence[str]) -> list[str]:
        return [n for n in dict.fromkeys(names) if n.casefold() != actor.casefold()]

    sentences = []
    for outcome, template in _ACTOR_TEMPLATES:
        names = others([c.name for c in changes or () if c.outcome == outcome])
        if names:
            sentences.append(template.format(actor=actor, names=join_names(names)))
    for change in changes or ():
        if (
            change.outcome in (Outcome.REMOVED, Outcome.REMOVED_MAYBE)
            and others([change.name]) != []
        ):
            sentences.append(ACTOR_REMOVED.format(actor=actor, name=change.name))
    if swap is not None and swap.outcome == SwapOutcome.SWAPPED:
        if len(others([swap.x, swap.y])) == 2:
            sentences.append(ACTOR_SWAPPED.format(actor=actor, x=swap.x, y=swap.y))
    return "\n".join(sentences) or None
