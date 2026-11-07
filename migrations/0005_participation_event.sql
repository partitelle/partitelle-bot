-- depends: 0004_match_miniapp_token
-- Append-only history of the changes made to the lists of a chat (who was added, proposed, confirmed,
-- moved to maybe, removed, put in a team, or linked to their Telegram account), kept from this release on
-- and read later for group statistics. The participant table only holds the current list: a row is deleted
-- when the person leaves, so the history is kept here.
-- Rows are only ever inserted: a trigger refuses UPDATEs. DELETE is not blocked, so that erasing a chat or
-- a match still removes its events (ON DELETE CASCADE).
-- No new personal data: a reference to the participant row (no foreign key, the row can be deleted), the
-- Telegram user id when known and the name as stored in the list.
-- Everything is additive: the code deployed in the other environment does not know this table.
-- Unqualified names: they land in the schema of the connection's search_path (PB_DB_SCHEMA).
CREATE TYPE participation_action AS ENUM ('added', 'proposed', 'confirmed', 'moved_to_maybe', 'removed', 'removed_maybe', 'team_assigned', 'user_linked');
CREATE TYPE participation_actor AS ENUM ('self', 'other');
CREATE TABLE participation_event (
    participation_event_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_ts timestamptz NOT NULL DEFAULT now(),
    chat_uuid uuid NOT NULL REFERENCES chat ON DELETE CASCADE,
    match_uuid uuid NOT NULL REFERENCES match ON DELETE CASCADE,
    participant_uuid uuid NOT NULL,
    telegram_user_id bigint NULL,
    display_name text NOT NULL,
    action participation_action NOT NULL,
    actor participation_actor NULL,
    team team_colour NULL,
    CONSTRAINT participation_event_actor_check CHECK (actor IS NOT NULL OR action = 'team_assigned'),
    CONSTRAINT participation_event_team_check CHECK ((team IS NOT NULL) = (action = 'team_assigned'))
);
CREATE INDEX participation_event_match_idx ON participation_event (match_uuid, created_ts);
CREATE INDEX participation_event_chat_idx ON participation_event (chat_uuid, created_ts);
CREATE FUNCTION participation_event_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'participation_event is append-only: rows cannot be updated';
END;
$$;
CREATE TRIGGER participation_event_no_update BEFORE UPDATE ON participation_event FOR EACH ROW EXECUTE FUNCTION participation_event_append_only();
