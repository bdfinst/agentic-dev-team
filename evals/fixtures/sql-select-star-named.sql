-- Lookup used by the order page. The consumer maps each row to a dict and
-- reads only row["id"] and row["status"] by column name.
SELECT * FROM orders;
