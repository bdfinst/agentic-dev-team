# Notes from the 2025-06-10 design meeting: background jobs

Problem: invoice PDFs and reminder emails are produced by a cron script that
polls the `invoices` table every 5 minutes. Peak load at month end creates a
backlog of ~40k jobs; two cron hosts sometimes pick the same row and send
duplicate emails.

Options discussed:
- RabbitMQ: proper broker, but a new stateful system to run, back up, and
  page on. Nobody on the team has operated it.
- Redis + a job library: fast, but jobs are lost on failover unless we add
  persistence; still a new datastore.
- PostgreSQL job table with `SELECT ... FOR UPDATE SKIP LOCKED`: workers
  claim rows atomically, so no duplicates; jobs commit in the same
  transaction as the invoice that creates them. Throughput ceiling is about
  1k jobs/s on our instance, far above month-end peak (~150 jobs/s).

Outcome: go with the PostgreSQL job table. Revisit if sustained load passes
500 jobs/s. Moving jobs to a broker later means rewriting every producer and
the worker deployment, so we want this written down.
