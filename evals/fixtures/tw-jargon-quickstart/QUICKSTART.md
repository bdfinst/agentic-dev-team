# Quickstart

It is imperative that the requisite dependencies be provisioned prior to the
utilization of the development environment, which is accomplished by
executing `make deps`, an operation which is idempotent and can therefore be
re-run without deleterious consequences should any failure be encountered.

The database is seeded by `make seed`. Seeding is effectuated against the
local Postgres instance on port 5433 (not the default 5432, so as to obviate
conflicts with any pre-existing installation), and it should be noted that
the seed corpus comprises approximately 200 synthetic customer records.

Subsequently, the application server may be instantiated via `make run`,
whereupon it will be accessible at http://localhost:8000. A heuristic
health-check endpoint is exposed at `/healthz`; a 200 response is
indicative of nominal operation.
