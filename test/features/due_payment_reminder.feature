@payment-reminder
Feature: Due payment reminders
  Whenever the due reminders are sent, the bot reads the database only: a match is due when it is on
  (enough confirmed players), it started between 08:00 of the day before and 08:00 of the day of the run
  (Europe/Rome) and its reminder was not sent yet. /stop does not matter.
  The reminder is sent and pinned once; a chat where sending fails is retried by the next run.

  Background:
    Given the user "@mario"
    And today is "2026-10-21 09:00"
    And the text "payment reminder" is:
      """
      Ciao bestie 😎, com'è andata la partita? C'è qualcuno che non ha ancora pagato la sua quota?
      """

  Scenario: a full match that started yesterday evening is reminded once and the reminder is stored
    Given a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And the payment reminder of "Calcetto" should be recorded as message 3 and the summary should stay message 2

  Scenario: a match that is not on is skipped and nothing is stored
    Given a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 3
    And the match has the players "ana, bea, carla (maybe)"
    And the match starts at "2026-10-20 21:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: a match stopped after kick-off is still reminded
    Given a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    And "@mario" had sent "/stop"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And the payment reminder of "Calcetto" should be recorded as message 5 and the summary should stay message 2

  Scenario: the window starts at 08:00 yesterday and ends before 08:00 today
    Given a group chat "Before"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 07:59"
    And a group chat "Inside"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 08:00"
    And a group chat "After"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-21 08:00"
    When the due payment reminders are sent
    Then the current chat is "Inside"
    And the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And no payment reminder should be recorded for "Before"
    And the payment reminder of "Inside" should be recorded as message 3 and the summary should stay message 2
    And no payment reminder should be recorded for "After"

  Scenario: a run before 08:00 looks at the previous window
    Given the clock moves to "2026-10-21 07:30"
    And a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 0 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: a second run sends nothing
    Given a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    When the due payment reminders are sent
    And the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 0 sent, 0 skipped and 0 failed
    And the payment reminder of "Calcetto" should be recorded as message 3 and the summary should stay message 2

  Scenario: a chat where sending fails is counted, released and does not stop the others
    Given a group chat "Broken"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 20:00"
    And a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    And Telegram refuses the next message the bot sends
    When the due payment reminders are sent
    Then the current chat is "Broken"
    And the bot should send the plain text "payment reminder"
    And the bot should log the warning "Could not send a payment reminder: BadRequest"
    And the current chat is "Calcetto"
    And the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 1 failed
    And no payment reminder should be recorded for "Broken"
    And the payment reminder of "Calcetto" should be recorded as message 3 and the summary should stay message 2

  Scenario: a chat where sending failed is reminded by the next run
    Given a group chat "Calcetto"
    And a match was started
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    And Telegram refuses the next message the bot sends
    When the due payment reminders are sent
    And the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should log the warning "Could not send a payment reminder: BadRequest"
    And the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And the payment reminder of "Calcetto" should be recorded as message 3 and the summary should stay message 2

  Scenario: a reminder that cannot be pinned still counts as sent
    Given a group chat "Calcetto"
    And a match was started
    And the bot is not an administrator of the chat
    And the match summary is the message 2
    And the match target is 2
    And the match has the players "ana, bea"
    And the match starts at "2026-10-20 21:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should log the warning "No admin rights to pin the message"
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And the payment reminder of "Calcetto" should be recorded as message 3 and the summary should stay message 2
