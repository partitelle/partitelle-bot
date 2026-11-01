"""TLS mode of the database connections: `require` by default, overridable with PB_DB_SSLMODE."""

import importlib

import pytest

from conf import conf
from db import connection as db_connection
from db import migrate as db_migrate


@pytest.fixture
def reload_conf(monkeypatch):
    """Reload `conf.conf` with PB_DB_SSLMODE set (a value) or unset (None); restore it afterwards."""

    def _reload(value):
        if value is None:
            monkeypatch.delenv("PB_DB_SSLMODE", raising=False)
        else:
            monkeypatch.setenv("PB_DB_SSLMODE", value)
        return importlib.reload(conf).db_sslmode

    yield _reload
    monkeypatch.undo()
    importlib.reload(conf)


def test_the_default_sslmode_is_require(reload_conf):
    assert reload_conf(None) == "require"


def test_an_empty_sslmode_falls_back_to_require(reload_conf):
    assert reload_conf("") == "require"


def test_the_sslmode_can_be_overridden(reload_conf):
    assert reload_conf("prefer") == "prefer"


def test_the_test_setup_disables_tls_for_the_local_database():
    assert conf.db_sslmode == "disable"


@pytest.mark.parametrize("mode", ["require", "disable"])
def test_the_pool_connects_with_the_configured_sslmode(monkeypatch, mode):
    created = {}

    class FakePool:
        check_connection = None

        def __init__(self, **kwargs):
            created.update(kwargs)

        def open(self, **kwargs):
            raise db_connection.PoolTimeout("stop here")

        def close(self):
            pass

    monkeypatch.setattr(db_connection, "ConnectionPool", FakePool)
    monkeypatch.setattr(db_connection, "db_sslmode", mode)
    with pytest.raises(db_connection.DatabaseUnavailable):
        db_connection._create_pool()
    assert created["kwargs"]["sslmode"] == mode


@pytest.mark.parametrize("mode", ["require", "disable"])
def test_the_migration_connections_use_the_configured_sslmode(monkeypatch, mode):
    monkeypatch.setattr(db_migrate, "db_sslmode", mode)
    monkeypatch.setattr(db_migrate, "host", "db.example")
    monkeypatch.setattr(db_migrate, "database", "partitelle")
    monkeypatch.setattr(db_migrate, "port", "5432")
    monkeypatch.setattr(db_migrate, "user", "u")
    monkeypatch.setattr(db_migrate, "password", "p")
    assert db_migrate.build_uri("staging") == (
        f"postgresql+psycopg://u:p@db.example:5432/partitelle?schema=staging&sslmode={mode}"
    )

    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query):
            pass

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(db_migrate.psycopg, "connect", fake_connect)
    db_migrate.create_schema("staging")
    assert captured["sslmode"] == mode
