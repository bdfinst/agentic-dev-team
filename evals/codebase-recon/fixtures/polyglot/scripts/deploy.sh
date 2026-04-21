#!/usr/bin/env bash
# Deploy the polyglot fixture to the staging environment.
# Usage: scripts/deploy.sh [target]
set -euo pipefail

TARGET="${1:-staging}"

echo "Deploying to ${TARGET} ..."
rsync -az backend/ "deploy@${TARGET}:/srv/app/backend/"
rsync -az frontend/dist/ "deploy@${TARGET}:/srv/www/"

ssh "deploy@${TARGET}" 'systemctl restart app.service'
echo "Done."
