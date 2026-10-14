# Migrations

Schema changes follow expand, migrate, contract:

1. Expand: add new tables or nullable columns that running code ignores.
2. Migrate: backfill data and move code to the new shape.
3. Contract: drop the old shape in a later revision, once no running code reads it.

- Apply: `make migrate` (reads `DATABASE_URL` from `.env`).
- New revision: `uv run --env-file .env python -m alembic revision --autogenerate --rev-id 0002 -m "<change>"`, then review the file. Alembic config lives under `[tool.alembic]` in the root `pyproject.toml`.
- Revisions live in `packages/db/src/filinglens_db/migrations/versions/`.
- `make test-int` upgrades an empty database to head, downgrades to base, upgrades again, and fails if the models and the migrations disagree.

## Log

| Revision | Phase | Change |
| --- | --- | --- |
| 0001 | expand | Enable the `vector` extension. Create `companies` (CIK primary key, ticker, name). |
