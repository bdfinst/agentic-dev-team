# customer-platform

Two services, `crm` and `support`, are deployed independently (separate
pipelines, different release days) and share the `customers` table in one
PostgreSQL database. Nightly jobs live in `jobs/` and run from the database
host's cron.
