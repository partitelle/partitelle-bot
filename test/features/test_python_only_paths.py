"""Paths the Gherkin scenarios do not describe (/bamboo, Telegram rejecting a summary, the db guard on names), exercised through the same
fake Telegram world. Plain pytest on purpose: the .feature files are the contract and are not touched."""

PRIVACY_LINE = "Come usiamo i tuoi dati: https://partitelle.com/privacy"
PRIVACY_LINE = "Come usiamo i tuoi dati: https://partitelle.com/privacy"
BAMBOO_GREETING = (
    "Ciao bestie 😎, chi c'è per il prossimo calcetto? \n"
    "\n"
    "- se sei in forse scrivi _proponimi_, \n"
    "- se vuoi proporre qualcuno scrivi _proponi <nome>_, \n"
    "- per essere aggiunto o confermato rispondi _aggiungimi_,\n"
    "- per aggiungere o confermare qualcuno usa _aggiungi <nome>_,\n"
    "- per essere rimosso _toglimi_, \n"
    "- per rimuovere qualcuno _togli <nome>_, \n"
    "- per modificare le squadre scrivi _scambia <nome 1> con <nome 2>_. \n\n"
    "Posso anche pinnare i messaggi se vuoi ma per farlo ricordati di aggiungermi come amministratore.\n"
    "\n" + PRIVACY_LINE
)
BAD_FORMATTING = "Bring *shoes and _balls"
PARSE_ERROR = (
    "can't parse entities: Can't find end of the entity starting at byte offset 40"
)


def test_bamboo_creates_the_match_with_the_bamboo_defaults_once(world):
    world.add_chat("Bamboo")
    world.add_user("@giulia", "Giulia", "giulia")

    world.send("@giulia", "/bamboo")

    greeting = world.next_call()
    assert greeting.method == "send_message"
    assert greeting.params["parse_mode"] == "markdown"
    assert greeting.params["text"] == BAMBOO_GREETING
    assert greeting.params["link_preview_options"] == {"is_disabled": True}
    match = world.db.fetch_match(world.current_chat.id)
    assert match["pitch"].startswith("Crespi Sport Village")
    assert match["day"].startswith("Mercoledì ")

    world.db.set_pitch(world.current_chat.id, "Altro campo")
    world.send("@giulia", "/bamboo")  # already there: answered, not recreated
    assert world.next_call().method == "send_message"
    assert world.db.fetch_match(world.current_chat.id)["pitch"] == "Altro campo"
    assert not world.unconsumed()


def test_new_summary_rejected_by_telegram_is_resent_as_plain_text(world):
    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    world.send("@giulia", f"/setdescription {BAD_FORMATTING}")
    world.forget_calls()
    world.telegram.fail_next("send_message", PARSE_ERROR)

    world.send("@giulia", "/participants")

    rejected, plain = world.next_call(), world.next_call()
    assert rejected.failed
    assert rejected.params["parse_mode"] == "markdown"
    assert plain.method == "send_message"
    assert "parse_mode" not in plain.params
    assert plain.params["text"] == rejected.params["text"]
    assert BAD_FORMATTING in plain.params["text"]
    pin = world.next_call()  # the plain summary is the tracked one, so it is pinned
    assert pin.method == "pin_chat_message"
    assert pin.params["message_id"] == world.last_bot_message_id()
    assert not world.unconsumed()


def test_summary_edit_rejected_by_telegram_is_resent_as_plain_text(world):
    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    world.send("@giulia", "/participants")  # tracks a summary message
    world.forget_calls()
    world.telegram.fail_next("edit_message_text", PARSE_ERROR)

    world.send("@giulia", f"/setdescription {BAD_FORMATTING}")

    confirmation, rejected, plain = (
        world.next_call(),
        world.next_call(),
        world.next_call(),
    )
    assert confirmation.method == "send_message"
    assert rejected.method == "edit_message_text" and rejected.failed
    assert rejected.params["parse_mode"] == "markdown"
    assert plain.method == "edit_message_text"
    assert "parse_mode" not in plain.params
    assert plain.params["message_id"] == rejected.params["message_id"]
    assert plain.params["text"] == rejected.params["text"]
    assert BAD_FORMATTING in plain.params["text"]
    assert world.next_call().method == "pin_chat_message"
    assert not world.unconsumed()


def test_another_telegram_error_on_the_summary_is_not_hidden(world):
    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    world.forget_calls()
    world.telegram.fail_next("send_message", "chat not found")
    world.expect_failures = True

    world.send("@giulia", "/participants")

    assert [call.method for call in world.unconsumed()] == ["send_message"]
    assert len(world.errors) == 1


def test_summary_edit_survives_the_bot_not_being_admin(world):
    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    world.send("@giulia", "/participants")  # tracks a summary message
    world.telegram.can_pin = False
    world.forget_calls()

    world.send("@giulia", "setpitch")  # plain text, ignored
    world.send("@giulia", "/setpitch Campo Nuovo")

    methods = [call.method for call in world.unconsumed()]
    assert methods == ["send_message", "edit_message_text", "pin_chat_message"]


def test_the_db_layer_refuses_to_store_an_empty_or_command_name(world):
    import pytest
    from db.repository import add_participant
    from domain import Participant

    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    for name in ["", "  ", "/start", "/stop"]:
        with pytest.raises(ValueError):
            add_participant(world.current_chat.id, Participant(name))
    assert world.db.fetch_match(world.current_chat.id)["players"] is None


def test_a_reminder_claimed_by_a_concurrent_run_is_skipped_and_left_to_it(
    world, monkeypatch
):
    from datetime import UTC, datetime

    import behaviours.send_due_reminders as sender
    from db.repository import claim_reminder, find_reminder_candidates
    from domain.schedule import TIMEZONE

    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    world.forget_calls()
    world.db.set_target(world.current_chat.id, 2)
    world.db.set_players(world.current_chat.id, [("ana", False), ("bea", False)])
    now = datetime(2026, 10, 21, 9, tzinfo=TIMEZONE)
    world.db.set_starts(
        world.current_chat.id, datetime(2026, 10, 20, 21, tzinfo=TIMEZONE)
    )

    def found_then_claimed_elsewhere(start, end):
        candidates = find_reminder_candidates(start, end)
        assert [claim_reminder(c.match_uuid) for c in candidates] == [True]
        return candidates

    monkeypatch.setattr(
        sender, "find_reminder_candidates", found_then_claimed_elsewhere
    )

    counts = world.run(
        sender.send_due_reminders(world.application.bot, now.astimezone(UTC))
    )

    assert counts == {"sent": 0, "skipped": 1, "failed": 0}
    assert not world.unconsumed()
    assert world.db.fetch_reminder(world.current_chat.id)[:2] == (True, None)


def test_a_released_claim_can_be_taken_again_and_only_once(world):
    from db.repository import claim_reminder, release_reminder

    world.add_chat("Calcetto")
    world.add_user("@giulia", "Giulia", "giulia")
    world.send("@giulia", "/start")
    with world.db.conn.cursor() as cur:
        cur.execute("SELECT match_uuid FROM match")
        match_uuid = str(cur.fetchone()[0])

    assert [claim_reminder(match_uuid), claim_reminder(match_uuid)] == [True, False]
    release_reminder(match_uuid)
    assert world.db.fetch_reminder(world.current_chat.id)[0] is False
    assert claim_reminder(match_uuid) is True
