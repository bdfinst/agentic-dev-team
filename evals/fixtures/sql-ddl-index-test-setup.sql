-- tests/fixtures/setup.sql: builds the test database for the PostgreSQL
-- project. Not a migration; it runs on an empty database before each suite.
CREATE TABLE orders (id bigint PRIMARY KEY, status text);
CREATE INDEX ix_orders_status ON orders (status);
INSERT INTO orders (id, status) VALUES (1, 'new'::text);
