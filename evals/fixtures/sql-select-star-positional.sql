-- Nightly export. The export job reads every row by index:
-- row[0] is the order id, row[2] is the status, row[3] is the total.
SELECT * FROM orders;
