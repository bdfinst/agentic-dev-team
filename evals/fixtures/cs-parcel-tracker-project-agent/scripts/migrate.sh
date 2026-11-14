#!/bin/sh
# Applies each migration in src/db/migrations/ once, in filename order, and
# records it in schema_migrations so a re-run skips it.
set -eu
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
for file in src/db/migrations/*.sql; do
  name=$(basename "$file")
  applied=$(printf "SELECT 1 FROM schema_migrations WHERE filename = :'name';\n" |
    psql "$DATABASE_URL" -tA -v ON_ERROR_STOP=1 -v name="$name")
  if [ -z "$applied" ]; then
    { cat "$file"; printf "\nINSERT INTO schema_migrations (filename) VALUES (:'name');\n"; } |
      psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -v name="$name" --single-transaction
  fi
done
