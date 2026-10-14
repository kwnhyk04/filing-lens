-- make check-parallel-hnsw: a parallel HNSW build fits in the postgres container's /dev/shm.
-- Runs in a throwaway database, so the app's data is never touched. Fails with "could not
-- resize shared memory segment" when shm_size is too small (Docker's default is 64 MB).
\set ON_ERROR_STOP on
\set app :DBNAME
DROP DATABASE IF EXISTS hnsw_check;
CREATE DATABASE hnsw_check;
\c hnsw_check
CREATE EXTENSION vector;
-- 10k random 768-dimension vectors; referencing n makes Postgres draw a new vector per row.
CREATE TABLE items AS
SELECT (SELECT array_agg(random()) FROM generate_series(1, 768) WHERE n > 0)::vector(768) AS embedding
FROM generate_series(1, 10000) AS n;
ALTER TABLE items SET (parallel_workers = 2); -- plan two workers whatever the table size
SET max_parallel_maintenance_workers = 2;
-- A parallel build keeps its graph in shared memory of this size; shm_size 256mb leaves room.
SET maintenance_work_mem = '200MB';
CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops);
\c :app
DROP DATABASE hnsw_check;
\echo parallel HNSW build fits in shared memory
