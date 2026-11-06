-- Seed data for the orders table. Every INSERT names its columns.
INSERT INTO orders (id, name, status) VALUES (1, 'alpha', 'new');
INSERT INTO orders (id, name, status) VALUES (2, 'beta', 'pending'), (3, 'gamma', 'new');
INSERT INTO audit_log DEFAULT VALUES;
