"""Credentials of the migrations: dedicated ones when both are set, the runtime ones otherwise."""

from urllib.parse import quote

import pytest

from db import migrate as db_migrate


@pytest.fixture
def credentials(monkeypatch):
    """Runtime credentials, plus a setter for the optional migration ones."""
    monkeypatch.setattr(db_migrate, "user", "runtime_user")
    monkeypatch.setattr(db_migrate, "password", "runtime-pw")

    def set_migrate(user, password):
        monkeypatch.setattr(db_migrate, "migrate_user", user)
        monkeypatch.setattr(db_migrate, "migrate_password", password)

    set_migrate(None, None)
    return set_migrate


@pytest.fixture
def connect_kwargs(monkeypatch):
    """Capture the arguments `create_schema` passes to psycopg instead of connecting."""
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query):
            captured["executed"] = True

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(db_migrate.psycopg, "connect", fake_connect)
    return captured


def test_migrations_use_the_runtime_credentials_when_no_others_are_set(credentials):
    assert db_migrate.migration_credentials() == ("runtime_user", "runtime-pw")


def test_migrations_use_their_own_credentials_when_both_are_set(credentials):
    credentials("owner_user", "owner-pw")
    assert db_migrate.migration_credentials() == ("owner_user", "owner-pw")


@pytest.mark.parametrize(
    "only", [("owner_user", None), (None, "owner-pw"), ("owner_user", "")]
)
def test_only_one_migration_credential_is_an_error(credentials, only):
    credentials(*only)
    with pytest.raises(RuntimeError) as error:
        db_migrate.migration_credentials()
    message = str(error.value)
    assert (
        "PB_DB_MIGRATE_USER and PB_DB_MIGRATE_PASSWORD must be set together" in message
    )
    for secret in ("owner_user", "owner-pw", "runtime-pw"):
        assert secret not in message


def test_the_migrate_command_fails_before_connecting_with_half_credentials(
    credentials, connect_kwargs
):
    credentials("owner_user", None)
    with pytest.raises(RuntimeError, match="must be set together"):
        db_migrate.migrate()
    assert connect_kwargs == {}


def test_the_schema_is_created_with_the_runtime_credentials_by_default(
    credentials, connect_kwargs
):
    db_migrate.create_schema("staging")
    assert connect_kwargs["user"] == "runtime_user"
    assert connect_kwargs["password"] == "runtime-pw"


def test_the_schema_is_created_with_the_migration_credentials_when_set(
    credentials, connect_kwargs
):
    credentials("owner_user", "owner-pw")
    db_migrate.create_schema("staging")
    assert connect_kwargs["user"] == "owner_user"
    assert connect_kwargs["password"] == "owner-pw"


def test_yoyo_connects_with_the_runtime_credentials_by_default(
    credentials, monkeypatch
):
    monkeypatch.setattr(db_migrate, "host", "db.example")
    monkeypatch.setattr(db_migrate, "database", "partitelle")
    monkeypatch.setattr(db_migrate, "port", "5432")
    assert db_migrate.build_uri("staging") == (
        "postgresql+psycopg://runtime_user:runtime-pw@db.example:5432/partitelle?schema=staging"
    )


def test_yoyo_connects_with_the_migration_credentials_when_set(
    credentials, monkeypatch
):
    monkeypatch.setattr(db_migrate, "host", "db.example")
    monkeypatch.setattr(db_migrate, "database", "partitelle")
    monkeypatch.setattr(db_migrate, "port", "5432")
    credentials("owner_user", "p@ss/w:rd")
    assert db_migrate.build_uri("staging") == (
        f"postgresql+psycopg://owner_user:{quote('p@ss/w:rd', safe='')}"
        "@db.example:5432/partitelle?schema=staging"
    )
