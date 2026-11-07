-- depends: 0003_copy_legacy_data
-- Secret link token of a match for the Mini App: created lazily the first time the match summary is
-- shown, so it is nullable with no default and no backfill. Tokens are per match: a new match gets a new one.
-- Unqualified names: they land in the schema of the connection's search_path (PB_DB_SCHEMA).
ALTER TABLE match ADD COLUMN miniapp_token text NULL;
CREATE UNIQUE INDEX match_miniapp_token_idx ON match (miniapp_token) WHERE miniapp_token IS NOT NULL;
