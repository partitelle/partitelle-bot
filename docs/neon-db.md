# Neon database

The database is hosted on Neon Free (it used to be a Render free Postgres that expired every month, see [#79](https://github.com/partitelle/partitelle-bot/issues/79)). There is one Neon project per environment, so each has its own free quota (100 CU-hours/month). Each environment uses a schema (`staging`, `prod`) of the database `partitelle`; the structure comes from `migrations/` (see "Database migrations" in `CONTRIBUTING.md`), so no manual DDL is ever needed.

| Field | Value |
| --- | --- |
| Projects | one for staging, one for prod |
| Region | AWS Europe Central 1 (Frankfurt) |
| PostgreSQL version | 17 |
| Database | `partitelle` |
| Role | `partitelle_owner` |
| Expiry | none |
| Idle | scales to zero after 5 minutes, wakes on the next connection |

## Connecting

In the Neon console, open the project, click Connect and turn "Connection pooling" OFF: use the **direct** host (no `-pooler` in it). The pooled host rejects the `-c search_path` startup option that `db/connection.py` and yoyo use to select the schema.

## Env vars

Set in the Render environment groups `PB_ENV_VARS` (service `partitelle-bot`, prod) and `PB_TEST_ENV_VARS` (service `partitelle-bot-test`, staging):

| Var | Value |
| --- | --- |
| `PB_DB_HOST` | direct host of the environment's Neon project |
| `PB_DB_NAME` | `partitelle` |
| `PB_DB_USER` | `partitelle_owner` |
| `PB_DB_PASSWORD` | role password from the Neon console |
| `PB_DB_PORT` | `5432` |
| `PB_DB_SCHEMA` | `prod` / `staging` |
| `PB_DB_MIGRATE_USER` | optional: role that runs the migrations (see "Least-privilege roles") |
| `PB_DB_MIGRATE_PASSWORD` | optional: password of that role; set both or neither |

`PB_DB_USER`/`PB_DB_PASSWORD` are what the bot uses at runtime. The migrations use them too, unless `PB_DB_MIGRATE_USER` and `PB_DB_MIGRATE_PASSWORD` are set: they must be set together, otherwise `db.migrate` stops with an error.

Tables are created by the yoyo migrations at startup (start command `python3 -m db.migrate && python3 main.py`).

## Least-privilege roles

By default one role (`partitelle_owner`) both migrates and serves the bot, so a bug or a leaked runtime password can alter or drop the schema. The recommended setup splits the two:

- the owner role owns the schema objects and is used only by the migrations (`PB_DB_MIGRATE_USER`/`PB_DB_MIGRATE_PASSWORD`);
- an app role has only data permissions on the environment's schema and is used by the bot at runtime (`PB_DB_USER`/`PB_DB_PASSWORD`).

Run this once per environment (its own Neon project), connected to the database `partitelle` as the owner role, replacing `<schema>`, `<owner_role>` and `<app_role>` (never reuse a password between environments):

```sql
CREATE ROLE <app_role> LOGIN PASSWORD '<generated password>';

GRANT USAGE ON SCHEMA <schema> TO <app_role>;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA <schema> TO <app_role>;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA <schema> TO <app_role>;

-- tables and sequences created by future migrations (run by <owner_role>) get the same permissions
ALTER DEFAULT PRIVILEGES FOR ROLE <owner_role> IN SCHEMA <schema>
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <app_role>;
ALTER DEFAULT PRIVILEGES FOR ROLE <owner_role> IN SCHEMA <schema>
  GRANT USAGE, SELECT ON SEQUENCES TO <app_role>;
```

The app role cannot create, alter or drop tables.

Rollout order on the host, one environment at a time, staging first, then prod:

1. Create the app role with the SQL above.
2. In the environment group, set `PB_DB_MIGRATE_USER`/`PB_DB_MIGRATE_PASSWORD` to the owner role (the current `PB_DB_USER`/`PB_DB_PASSWORD` values). Deploy and check that the logs show `Migrations applied` or `is up to date`.
3. Set `PB_DB_USER`/`PB_DB_PASSWORD` to the app role and deploy. Check `GET /health` and a few commands in the bot.
4. Update the stats tracker secrets only if you also want it on a read-only role (see "Stats tracker").

Rollback: put the owner credentials back in `PB_DB_USER`/`PB_DB_PASSWORD` and deploy (the `PB_DB_MIGRATE_*` vars can stay). Staging validates a new migration against the app role: if a migration adds a table, check that the bot still works after it.

## Applying env var changes on Render

"Restart service" does NOT pick up changed env group values: a deploy does.

- Staging: Manual Deploy, "Deploy latest commit" (staging always runs `main`).
- Prod: deploy only the commit of the latest release. "Deploy latest commit" is safe only if `main` HEAD is the latest release tag; otherwise use Manual Deploy, "Deploy a specific commit" with the commit of the latest tag (`git tag --sort=-creatordate | head -1`). Never deploy unreleased code.

The deploy logs show `Applying to schema '<schema>': [...]` then `Migrations applied`.

## Stats tracker

The `partitelle-bot-stats-tracker` repo reads prod through its GitHub Actions secrets `PB_DB_HOST`, `PB_DB_NAME`, `PB_DB_USER`, `PB_DB_PASSWORD` (and `PB_DB_SCHEMA=prod` if present). Update them when the host or password changes.

## Manual export and restore

There are no scheduled backups and Neon Free keeps only a short restore window, so export before risky changes. Dumps contain personal data: keep them private and never commit them.

### Export

Dump the whole schema of the environment, including the yoyo tables (`_yoyo_*`): the migration history comes back with the data, so a restored schema is up to date and `db.migrate` does not try to apply the migrations again. Use the direct connection string, and `postgres:17` (a client older than the server fails).

```bash
docker run --rm postgres:17 pg_dump "<direct connection string>" \
  --schema=<schema> --format=custom --no-owner --no-privileges > <schema>-$(date +%F).dump
```

`--no-owner --no-privileges` (also needed on `pg_restore`, below) make the dump restorable by any role; run the grants from "Least-privilege roles" again after a restore into a new database.

### Store

- Encrypt it right away and delete the plain file, for example `age -p -o <schema>.dump.age <schema>.dump` or `gpg --symmetric <schema>.dump`. Keep the passphrase in your password manager, not next to the file.
- Keep it outside synced or shared folders (cloud drives, shared disks) and outside the repository.
- Delete old dumps when a newer one exists and once they are not needed: the data includes people's names.

### Restore test

Try the restore into a throwaway local Postgres before you need it, and compare the row counts:

```bash
docker run -d --rm --name pg-restore -e POSTGRES_PASSWORD=restore -p 55432:5432 postgres:17
docker exec pg-restore psql -U postgres -c "CREATE DATABASE restored"
docker exec -i pg-restore pg_restore -U postgres --dbname=restored --no-owner --no-privileges --exit-on-error < <schema>.dump
# an encrypted dump: age -d <schema>.dump.age | docker exec -i pg-restore pg_restore ... (same options)
```

Then compare each table with the source (replace `<table>` with `chat`, `match`, `participant`, ...):

```bash
docker run --rm postgres:17 psql "<direct connection string>" -Atc "SELECT count(*) FROM <schema>.<table>"
docker exec pg-restore psql -U postgres -d restored -Atc "SELECT count(*) FROM <schema>.<table>"
```

and check that `SELECT count(*) FROM <schema>._yoyo_migration` matches too. Stop the container at the end: `docker stop pg-restore`.

To restore into a real environment, restore into an empty schema (or a Neon branch) first, and only then decide how to switch; never restore over live data without a fresh export.

A DBeaver "SQL" export starts with `DROP TABLE`/`CREATE TABLE`: it is not a substitute for the dump above.

## Testing a migration on real data

1. In the prod Neon project, create a temporary branch of the default branch.
2. Run the migrations locally against it:

   ```bash
   PB_DB_HOST=<branch host> PB_DB_NAME=partitelle PB_DB_USER=partitelle_owner \
   PB_DB_PASSWORD=<password> PB_DB_PORT=5432 PB_DB_SCHEMA=prod \
   uv run python -m db.migrate
   ```

3. Check the result, then delete the branch.

## Troubleshooting

- Tables not visible in the Neon console: select the `prod`/`staging` schema, the default view shows `public`.
- `pg_dump: error: aborting because of server version mismatch`: the local client is older than the server. Use the `postgres:17` Docker image.
- Migrations fail at start: the bot does not start (the start command uses `&&`). Check the deploy logs for the failing migration.
- Changed env vars have no effect: a restart is not enough, deploy (see above).
