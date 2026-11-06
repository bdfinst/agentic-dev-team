-- Postgres schema and migration for the orders table.
CREATE TABLE orders (id bigint PRIMARY KEY, n bigint);

-- Migration 0007: shrink the counter column.
ALTER TABLE orders ALTER COLUMN n TYPE int;
