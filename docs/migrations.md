# Migrations

Schema changes follow expand, migrate, contract:

1. Expand: add new tables or nullable columns that running code ignores.
2. Migrate: backfill data and move code to the new shape.
3. Contract: drop the old shape in a later release, once no running code reads it.

- Apply: `make migrate` upgrades to head; `make migrate REV=0008` stops at a revision (dev uses it, see below). Both read `DATABASE_URL` from `.env`. To go back: `uv run --env-file .env python -m alembic downgrade <revision>`.
- New revision: `uv run --env-file .env python -m alembic revision --autogenerate --rev-id 0009 -m "<change>"`, then review the file. Alembic config lives under `[tool.alembic]` in the root `pyproject.toml`.
- Revisions live in `packages/db/src/filinglens_db/migrations/versions/`.
- `make test-int` upgrades an empty database to head, downgrades to base, upgrades again, and fails if the models and the migrations disagree. It also runs the embedding swap below from 0008 to 0006.

## Rules

- Every migration runs with `lock_timeout = '5s'`. `env.py` sets it on the migration connection with `SET` (not `SET LOCAL`), so autocommit blocks get it too. A statement that waits longer for a lock fails instead of queueing the app's queries behind it; run the migration again later.
- Build and drop indexes with `CREATE INDEX CONCURRENTLY` inside `op.get_context().autocommit_block()` (`op.create_index(..., postgresql_concurrently=True)`). Drop the index with `if_exists=True` before building it: a failed concurrent build leaves an invalid index behind, and the rerun then starts clean. New tables get only their keys in `CREATE TABLE`; their other indexes follow this rule too.
- Add columns as nullable without a default, so `ALTER TABLE` changes only the catalog.
- Migration statements time out after an hour (`env.py`); the app's 30 s limit would cancel index builds on a full table.
- Each revision runs in its own transaction (`transaction_per_migration` in `env.py`), so a failed revision leaves the earlier ones applied and stamped.

## Dev path: model A until the live swap

Dev, and the backend on the PC, stays on the last revision before the swap (now 0008) through steps 4-6, so the pipeline, search and the step 6 evals run on model A (`embedding`). After the step 6 evals, the swap below runs for real, and recall@10 is measured before and after.

- Migrate with `make migrate REV=0008`, and set `RETRIEVAL_EMBEDDING_COLUMN=embedding` in `.env` (as `.env.example` does).
- The swap revisions stay at the end of the chain until the live swap. A new revision revises the one 0004 revises today, and 0004 then revises the new one. That is why the chain runs 0001, 0002, 0003, 0007, 0008, 0004, 0005, 0006. The dev path then moves to the new revision.
- Code must run on the dev revision. It reads and writes embeddings through the column `RETRIEVAL_EMBEDDING_COLUMN` names, with that column's model from `EMBEDDING_MODELS`, as `nearest_chunks` does. It never uses `Chunk.embedding_v2`, which exists only from 0004 on. The ORM maps head's columns but defers the embedding ones, so loading chunks still works without them.
- `make seed-fake` fills whichever embedding columns exist.
- A plain `make migrate` goes to head: 0004 and 0005 only add, and 0006 refuses to drop model A while any chunk lacks `embedding_v2`. To return to the dev path: `uv run --env-file .env python -m alembic downgrade 0008`.
- CI checks every change on real data (`migrations` job in `.github/workflows/ci.yml`):
  1. Restore `corpus-v1.dump`, golden v1's corpus at the deployed revision (`make corpus-restore`).
  2. Upgrade to the dev path's target: the revision 0004 revises, read from the chain, so a new revision is picked up by itself.
  3. Downgrade one step, then upgrade again.

  An empty database's upgrade to head, its downgrade to base and `alembic check` stay in `test_migrations.py` (integration job). Run on 2026-10-17 on a restored copy: 0008, then 0008 to 0007 over 856,438 facts, then back to 0008. Never run these steps on the dev database: the downgrade drops the 0008 columns and their data. After the live swap the target becomes head.

The live swap, after step 6:

1. Baseline: run `make eval` with `RETRIEVAL_EMBEDDING_COLUMN=embedding`, and note recall@10 and MRR@10 with the golden set version.
2. Run steps 1-5 of the runbook below: 0004, the reembed backfill (it needs the step 6 embedding provider), 0005, the catch-up run, and the flip to `embedding_v2`.
3. Run `make eval` again on the same golden set version.
4. Record both runs: an `eval_runs` row each, and the activity log. If model B does worse, flip back to `embedding` and stop before the contract.
5. In the next release, run steps 6-7 (the 0006 contract) and set `RETRIEVAL_EMBEDDING_COLUMN=embedding_v2` in `.env.example`; the settings and compose defaults already use it.

## Embedding model swap

Chunks start on model A (`embedding`, BAAI/bge-small-en-v1.5, 384 dimensions) and move to model B (`embedding_v2`, BAAI/bge-base-en-v1.5, 768 dimensions). Search gets its column from `RETRIEVAL_EMBEDDING_COLUMN` on every query (`filinglens_retrieval.nearest_chunks`), and each column has its own HNSW index, so search stays on one complete index throughout.

Release N ships 0004 and 0005, with code that knows both columns:

1. Expand: `alembic upgrade 0004` adds nullable `embedding_v2` and `embedding_v2_model`. Rollback: `alembic downgrade 0008`.
2. Migrate: start the backfill once, with `docker compose exec ingest celery -A filinglens_ingest.worker call filinglens_ingest.reembed.reembed`. Each run embeds the next 256 chunks, in chunk id order, that model B has not embedded, then queues the next run with the last id. Runs are rate limited to 60 a minute; Celery's limit is per worker, but only one run is queued at a time. A crash or restart redelivers the message, and the run skips the rows already done. Progress: `SELECT count(*) FILTER (WHERE embedding_v2_model = 'BAAI/bge-base-en-v1.5'), count(*) FROM chunks;`
3. Index: when the backfill finishes, `alembic upgrade 0005` builds the HNSW index on `embedding_v2` concurrently. One build after the backfill is faster than updating the index row by row. Size the build first:
   - A parallel build keeps its graph in shared memory of about `maintenance_work_mem`. Compose gives postgres `shm_size: 256mb` in dev and prod, so keep `maintenance_work_mem` at 200 MB or less for a parallel build; `make check-parallel-hnsw` confirms on the dev stack that one fits. With Docker's default 64 MB it fails with "could not resize shared memory segment".
   - The graph needs about 4 KB per 768-dimension vector, so 200 MB holds about 50k. Past that, pgvector notes that the graph no longer fits and the rest of the build slows down.
   - A serial build (`SET max_parallel_maintenance_workers = 0`) keeps the graph in local memory instead, so `maintenance_work_mem` can be larger: the seed builds 100k vectors in 140 s with 512 MB. The prod memory limit (1.5 GB) covers `shm_size`, 512 MB of `maintenance_work_mem`, `shared_buffers` and connections; raise it before using more.
   - Measure the corpus first, then pick one of the two. Alembic opens its own session, so set the values on the database: `ALTER DATABASE <name> SET maintenance_work_mem = '200MB'` (and `max_parallel_maintenance_workers` for a serial build) before 0005, and `ALTER DATABASE <name> RESET ...` after it.
4. Catch up: start the task again. It embeds only the chunks ingested during the first pass.
5. Flip: set `RETRIEVAL_EMBEDDING_COLUMN=embedding_v2` in `.env` and recreate the API (`docker compose up -d api`); settings are read at startup. To roll back, set `embedding` again: both indexes stay until the contract step.

Release N+1, once every running API reads `embedding_v2`:

6. Check that `SELECT count(*) FROM chunks WHERE embedding_v2 IS NULL` returns 0; if not, run the task again.
7. Contract: deploy code that no longer reads `embedding`, then `alembic upgrade 0006`. It refuses to run while any chunk lacks `embedding_v2`, then drops `ix_chunks_embedding` concurrently and the old columns. Its downgrade restores an empty column and index only: re-embed with model A before pointing the flag back.

The next swap repeats these steps with a new column such as `embedding_v3`, added to `EmbeddingColumn` and `EMBEDDING_MODELS` in `filinglens_core.settings`.

## Log

| Revision | Phase | Change |
| --- | --- | --- |
| 0001 | expand | Enable the `vector` extension. Create `companies` (CIK primary key, ticker, name). |
| 0002 | expand | Add `companies.sector`. Create `filings` (status enum), `sections`, `chunks` (generated `tsv`, `embedding` vector(384)), `financial_facts`, `ingest_jobs`, `ingest_job_items`, `dead_letters` and `eval_runs`. |
| 0003 | expand | Concurrent indexes: HNSW (cosine) on `chunks.embedding`, GIN on `chunks.tsv`, `chunks (section_id, char_start)`, `filings (filed_on, accession_number)`, and `(created_at, id)` on `ingest_jobs`, `dead_letters` and `eval_runs`. |
| 0007 | expand | Create `ingest_job_companies` (job, CIK, discovery status, error), so a job knows when discovery is done. Revises 0003; 0004 revises it, which keeps the swap last. |
| 0008 | expand, plus one unused key dropped | Add nullable `filings.fiscal_source` (enum `companyfacts`, `period_of_report`), `filings.missing_items`, `sections.text` and `financial_facts.filed_on`. Build the unique index `uq_financial_facts_cik` (cik, taxonomy, concept, unit, period_end, period_start, accession number; `NULLS NOT DISTINCT`) concurrently, then drop the old key `uq_financial_facts_accession_number`: no code names it, and it would drop one registrant's facts from a combined filing. The new key holds the old one's columns, so building it cannot fail. The downgrade loses the new columns' data and fails while one filing reports a fact for two CIKs. Revises 0007; 0004 revises it. |
| 0004 | expand | Add nullable `chunks.embedding_v2` vector(768) and `chunks.embedding_v2_model`. |
| 0005 | expand | Concurrent HNSW (cosine) index on `chunks.embedding_v2`. |
| 0006 | contract | Drop `ix_chunks_embedding`, `chunks.embedding` and `chunks.embedding_model` (separate release). Refuses while any chunk lacks `embedding_v2`. |
