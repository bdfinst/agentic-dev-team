-- Postgres schema and migration for the orders table.
CREATE TABLE orders (id bigint PRIMARY KEY, n int);

-- Migration 0007: widen the counter column.
ALTER TABLE orders ALTER COLUMN n TYPE bigint;
