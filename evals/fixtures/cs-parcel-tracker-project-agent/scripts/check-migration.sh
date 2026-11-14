#!/bin/sh
# Blocks any Bash command that would drop a table outside a migration file.
set -eu
command_text=$(cat)
case "$command_text" in
  *"DROP TABLE"*) echo "DROP TABLE is allowed only inside src/db/migrations/" >&2; exit 2 ;;
esac
exit 0
