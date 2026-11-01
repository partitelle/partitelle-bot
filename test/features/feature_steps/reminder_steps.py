"""Steps for the payment reminder features (the due reminders, read from the database)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pytest_bdd import given, parsers, then, when

from behaviours.send_due_reminders import send_due_reminders

ROME = ZoneInfo("Europe/Rome")


# ---- due reminders, read from the database ------------------------------------------------------------


@given(parsers.parse('the match starts at "{when}"'))
def _match_starts(world, when):
    """YYYY-MM-DD HH:MM, Europe/Rome."""
    starts = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=ROME)
    world.db.set_starts(world.current_chat.id, starts)


@given(parsers.parse("the match summary is the message {message:d}"))
def _summary_message(world, message):
    world.db.set_summary_message_id(world.current_chat.id, message)


@given("Telegram refuses the next message the bot sends")
def _next_send_refused(world):
    world.telegram.fail_next("send_message", "chat not found")


@when("the due payment reminders are sent")
def _send_due(world):
    world.reminder_counts = world.run(
        send_due_reminders(world.application.bot, datetime.now(UTC))
    )


@then(
    parsers.parse(
        "the due reminders should count {sent:d} sent, {skipped:d} skipped and {failed:d} failed"
    )
)
def _counts(world, sent, skipped, failed):
    assert world.reminder_counts == {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }


@then(
    parsers.parse(
        'the payment reminder of "{title}" should be recorded as message {message:d} '
        "and the summary should stay message {summary:d}"
    )
)
def _reminder_recorded(world, title, message, summary):
    sent, reminder_id, summary_id = world.db.fetch_reminder(world.chats[title].id)
    assert sent, "reminder_sent_ts is still empty"
    assert (reminder_id, summary_id) == (message, summary), (reminder_id, summary_id)


@then(parsers.parse('no payment reminder should be recorded for "{title}"'))
def _reminder_not_recorded(world, title):
    sent, reminder_id, _ = world.db.fetch_reminder(world.chats[title].id)
    assert (sent, reminder_id) == (False, None)
