"""Migration 0005: the participation log table is created, constrained, and fully removed by its rollback."""

import os
import uuid

import psycopg
import pytest
from psycopg import errors, sql
from yoyo import get_backend, read_migrations

from db import migrate as db_migrate

MIGRATION = "0005_participation_event"
ENUMS = {"participation_action", "participation_actor"}


@pytest.fixture
def schema():
    name = f"schema_event_{uuid.uuid4().hex[:8]}"
    db_migrate.create_schema(name)
    with psycopg.connect(
        host=os.environ["PB_DB_HOST"],
        port=os.environ["PB_DB_PORT"],
        user=os.environ["PB_DB_USER"],
        password=os.environ["PB_DB_PASSWORD"],
        dbname=os.environ["PB_DB_NAME"],
        options=f"-c search_path={name}",
        autocommit=True,
    ) as conn:
        try:
            yield name, conn
        finally:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name))
            )


def objects(conn, schema_name):
    """Names of what the migration creates that exist in the schema."""
    return {
        "table": conn.execute("SELECT to_regclass('participation_event')").fetchone()[
            0
        ],
        "enums": {
            row[0]
            for row in conn.execute(
                "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = %s AND t.typtype = 'e' AND t.typname LIKE 'participation_%%'",
                [schema_name],
            )
        },
        "functions": {
            row[0]
            for row in conn.execute(
                "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = %s AND p.proname LIKE 'participation_%%'",
                [schema_name],
            )
        },
        "indexes": {
            row[0]
            for row in conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s "
                "AND tablename = 'participation_event'",
                [schema_name],
            )
        },
        "triggers": {
            row[0]
            for row in conn.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgrelid = to_regclass('participation_event')"
            )
        },
    }


def test_the_migration_creates_the_log_and_the_rollback_removes_it_all(schema):
    name, conn = schema
    backend = get_backend(db_migrate.build_uri(name))
    migrations = read_migrations(str(db_migrate.MIGRATIONS_DIR))
    # the rollback file is not a migration of its own
    assert [m.id for m in migrations][-1] == MIGRATION
    assert len([m for m in migrations if "rollback" in m.id]) == 0

    backend.apply_migrations(backend.to_apply(migrations))
    assert objects(conn, name) == {
        "table": "participation_event",
        "enums": ENUMS,
        "functions": {"participation_event_append_only"},
        "indexes": {
            "participation_event_pkey",
            "participation_event_match_idx",
            "participation_event_chat_idx",
        },
        "triggers": {"participation_event_no_update"},
    }

    only_this = migrations.filter(lambda m: m.id == MIGRATION)
    backend.rollback_migrations(backend.to_rollback(only_this))
    assert objects(conn, name) == {
        "table": None,
        "enums": set(),
        "functions": set(),
        "indexes": set(),
        "triggers": set(),
    }
    assert [m.id for m in backend.to_apply(migrations)] == [MIGRATION]

    backend.apply_migrations(backend.to_apply(migrations))
    assert objects(conn, name)["table"] == "participation_event"


def test_the_constraints_keep_actor_and_team_consistent(schema):
    name, conn = schema
    backend = get_backend(db_migrate.build_uri(name))
    backend.apply_migrations(
        backend.to_apply(read_migrations(str(db_migrate.MIGRATIONS_DIR)))
    )
    chat = conn.execute(
        "INSERT INTO chat (telegram_chat_id) VALUES (1) RETURNING chat_uuid"
    ).fetchone()[0]
    match = conn.execute(
        "INSERT INTO match (chat_uuid, starts_ts, target) "
        "VALUES (%s, now(), 4) RETURNING match_uuid",
        [chat],
    ).fetchone()[0]

    def insert(action, actor, team):
        conn.execute(
            "INSERT INTO participation_event (chat_uuid, match_uuid, participant_uuid, "
            "display_name, action, actor, team) VALUES (%s, %s, gen_random_uuid(), 'a', "
            "%s::participation_action, %s::participation_actor, %s::team_colour)",
            [chat, match, action, actor, team],
        )

    insert("team_assigned", None, "black")
    insert("added", "other", None)
    insert("user_linked", "self", None)
    for action, actor, team in [
        ("added", None, None),  # only a team assignment has no actor
        ("team_assigned", "self", None),  # a team assignment needs its team
        ("added", "self", "white"),  # no team on the other actions
    ]:
        with pytest.raises(errors.CheckViolation):
            insert(action, actor, team)
    assert conn.execute("SELECT count(*) FROM participation_event").fetchone() == (3,)
