import pytest

from behaviours.replies import remove_names_reply, remove_reply
from domain import Change, Outcome

REMOVED = Outcome.REMOVED
MAYBE = Outcome.REMOVED_MAYBE
NOT_IN = Outcome.NOT_IN


def _reply(*pairs):
    names = [name for name, _ in pairs]
    return remove_names_reply(names, [Change(outcome, name) for name, outcome in pairs])


@pytest.mark.parametrize(
    "pairs, expected",
    [
        ([("luca", REMOVED), ("anna", REMOVED)], "Che vergogna, luca e anna"),
        (
            [("bea", MAYBE), ("ivo", MAYBE)],
            "Davvero? Ma bea e ivo, ne siete proprio sicuri?",
        ),
        (
            [("carlo", NOT_IN), ("dario", NOT_IN)],
            "carlo e dario non sono nella lista. Chi dovrei togliere?",
        ),
        (
            [("luca", REMOVED), ("bea", MAYBE)],
            "Che vergogna, luca. Davvero? Ma bea, ne sei proprio sicuro?",
        ),
        (
            [("luca", REMOVED), ("carlo", NOT_IN), ("dario", NOT_IN)],
            "Che vergogna, luca. carlo e dario non sono nella lista",
        ),
        (
            [("bea", MAYBE), ("carlo", NOT_IN)],
            "Davvero? Ma bea, ne sei proprio sicuro? carlo non è nella lista",
        ),
        (
            [("a", REMOVED), ("b", REMOVED), ("c", REMOVED)],
            "Che vergogna, a, b e c",
        ),
        # typed order inside a group, whatever the order of the outcomes
        (
            [("bea", MAYBE), ("luca", REMOVED), ("anna", REMOVED)],
            "Che vergogna, luca e anna. Davvero? Ma bea, ne sei proprio sicuro?",
        ),
    ],
)
def test_remove_names_reply(pairs, expected):
    assert _reply(*pairs) == expected


def test_names_are_deduplicated():
    changes = [Change(REMOVED, "luca")]
    assert remove_names_reply(["luca", "luca"], changes) == "Che vergogna, luca"


def test_markdown_is_escaped():
    assert _reply(("a_b", REMOVED)) == "Che vergogna, a\\_b"


def test_single_name_replies_are_unchanged():
    assert remove_reply("luca", Change(REMOVED, "luca")) == "Che vergogna, luca"
    assert (
        remove_reply("luca", Change(MAYBE, "luca"))
        == "Davvero? Ma luca, ne sei proprio sicuro?"
    )
    expected = "luca non è nella lista. Chi dovrei togliere?"
    assert remove_reply("luca", Change(NOT_IN, "luca")) == expected
    assert remove_reply("luca", None) == expected
