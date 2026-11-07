-- Undoes 0005_participation_event, one statement per statement of the migration, in reverse order.
DROP TRIGGER participation_event_no_update ON participation_event;
DROP FUNCTION participation_event_append_only();
DROP INDEX participation_event_chat_idx;
DROP INDEX participation_event_match_idx;
DROP TABLE participation_event;
DROP TYPE participation_actor;
DROP TYPE participation_action;
