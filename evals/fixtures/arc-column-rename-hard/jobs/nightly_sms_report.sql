-- Runs at 02:00 from cron on the database host.
COPY (
  SELECT id, name, phone
  FROM customers
  WHERE phone IS NOT NULL AND sms_opt_in
) TO '/var/exports/sms_recipients.csv' WITH CSV HEADER;
