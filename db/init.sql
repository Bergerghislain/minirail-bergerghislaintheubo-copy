-- Runs once when the PostgreSQL container initializes (docker-entrypoint-initdb.d).
-- pgmq backs the task queue (remoulade's PostgresBroker); pg_partman manages
-- the queue archive partitions.
CREATE EXTENSION IF NOT EXISTS pg_partman CASCADE;
CREATE EXTENSION IF NOT EXISTS pgmq CASCADE;
