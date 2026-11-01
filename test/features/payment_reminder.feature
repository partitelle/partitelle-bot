@payment-reminder
Feature: Payment reminder after a match
  The reminder is not scheduled by the commands: the daily run reads the database and reminds every
  group whose match is on (the list reached the target), started in the 08:00 to 08:00 window
  (Europe/Rome) and was not reminded yet. These scenarios drive the real commands and then run the
  due reminders the morning after the match, so they check that the reminder follows the state the
  commands left, whatever the order of /setnumber, /setday, /settime, joining, leaving and /stop.

  Background:
    Given a group chat "Calcetto"
    And the user "@mario"
    And today is "2026-10-21 21:00"
    And the text "default description" is:
      """
      5 goal di scarto e le squadre si _potrebbero_ cambiare 
      6 goal di scarto e le squadre si *devono* cambiare 
      (ditelo a chiunque invitate) 
      *PORTARE UNA MAGLIA BIANCA E UNA COLORATA*

      """
    And the text "campo" is:
      """
      *CAMPO*: 
      Usa il comando /setpitch <campo> per inserire la struttura sportiva dove giocherete.
      """
    And the text "payment reminder" is:
      """
      Ciao bestie 😎, com'è andata la partita? C'è qualcuno che non ha ancora pagato la sua quota?
      """
    And the text "kickoff" is:
      """
      🚀 *SI GIOCA* 🚀 facciamo le squadre? /teams 😎
      """

  Scenario: Joining until the target is reached sends the reminder the morning after the match
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed

  Scenario: Lowering the target to the number of players sends the reminder the morning after the match
    Given a match was started
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "/setnumber 2"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed

  Scenario: A match whose day and time were changed several times is reminded once
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "/setday 19/10/2026"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "/settime 21:30"
    And "@mario" had sent "/settime 22:30"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    And the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 0 sent, 0 skipped and 0 failed

  Scenario: /setday on an incomplete list does not remind a match that may never be played
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "/setday 20/10/2026"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: /settime on an incomplete list does not remind a match that may never be played
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "/settime 21:30"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: Removing a player before the teams are drawn leaves no reminder for the incomplete list
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "togli anna"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: Removing a player after the teams were formed leaves no reminder until the target is reached again
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "/teams"
    And "@mario" had sent "togli anna"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"
    When "@mario" sends "aggiungi anna"
    Then the bot should send:
          """
          Ok, aggiungo anna
          """
    And the bot should edit the summary to:
          """
          *GIORNO*: Martedì 20/10/2026 | 20:00

          1. bruno ✅
          2. anna ✅

          {default description}

          {campo}
          """
    And the bot should pin the summary
    And the bot should send the text "kickoff"
    And the bot should send nothing else
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed

  Scenario: Raising the target above the number of players leaves no reminder
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "/setnumber 4"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 1 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: /stop after the match was on does not cancel the reminder
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And "@mario" had sent "/stop"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed

  Scenario: A match that starts later than the window is not reminded yet
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send nothing else
    And the due reminders should count 0 sent, 0 skipped and 0 failed
    And no payment reminder should be recorded for "Calcetto"

  Scenario: After the reminder was sent, the next summary update edits the summary, not the reminder
    Given a match was started
    And "@mario" had sent "/setnumber 2"
    And "@mario" had sent "/setday 20/10/2026"
    And "@mario" had sent "aggiungi anna"
    And "@mario" had sent "aggiungi bruno"
    And the clock moves to "2026-10-21 09:00"
    When the due payment reminders are sent
    Then the bot should send the plain text "payment reminder"
    And the bot should pin the last message
    And the bot should send nothing else
    And the due reminders should count 1 sent, 0 skipped and 0 failed
    And the match summary message should not be the last message of the bot
    When "@mario" sends "/setpitch Crespi"
    Then the bot should send:
          """
          Ok, @mario! Ho aggiornato il campo!
          """
    And the bot should edit the summary to:
          """
          *GIORNO*: Martedì 20/10/2026 | 20:00

          1. anna ✅
          2. bruno ✅

          {default description}

          *CAMPO*: 
          Crespi
          """
    And the bot should pin the summary
    And the bot should send nothing else
