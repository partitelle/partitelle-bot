"""Steps for the payment reminder feature (scheduled job asserted at behaviour level)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pytest_bdd import given, parsers, then, when

from behaviours.send_due_reminders import send_due_reminders

ROME = ZoneInfo("Europe/Rome")


# ---- helpers ----------------------------------------------------------------------------------------


def _reminders_of_this_chat(world):
    """Fire times (Europe/Rome, 'YYYY-MM-DD HH:MM') of the reminders scheduled for the current chat."""
    name = str(world.current_chat.id)
    return sorted(
        job.job.trigger.run_date.astimezone(ROME).strftime("%Y-%m-%d %H:%M")
        for job in world.job_queue.jobs()
        if job.name == name
    )


# ---- Then: scheduled reminders ----------------------------------------------------------------------


@then(parsers.parse('a payment reminder should be scheduled for "{when}"'))
def _one_reminder(world, when):
    assert _reminders_of_this_chat(world) == [when], (
        f"Expected exactly one reminder at {when}, got {_reminders_of_this_chat(world)}"
    )


@then(
    parsers.re(
        r'(?P<count>\d+) payment reminders should be scheduled for "(?P<when>[^"]+)"$'
    )
)
def _many_reminders(world, count, when):
    assert _reminders_of_this_chat(world) == [when] * int(count), (
        f"Expected {count} reminders at {when}, got {_reminders_of_this_chat(world)}"
    )


@then("no payment reminder should be scheduled")
def _no_reminder(world):
    assert _reminders_of_this_chat(world) == [], (
        f"Unexpected reminder(s): {_reminders_of_this_chat(world)}"
    )


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
