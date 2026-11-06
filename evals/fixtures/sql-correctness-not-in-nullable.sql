-- Orders that were never shipped.
CREATE TABLE u (t_id int NULL);
SELECT id FROM t WHERE id NOT IN (SELECT t_id FROM u);
