#!/usr/bin/env bash
# Usage: deploy.sh <staging|production>
set -euo pipefail
ENV="$1"

# Build a fresh image for this environment.
git pull origin main
docker build -t registry.example.com/orders:"$ENV" .
docker push registry.example.com/orders:"$ENV"

# Apply database migrations.
docker run --rm registry.example.com/orders:"$ENV" python manage.py migrate

# Restart every instance at once with the new image.
for host in $(cat "hosts/$ENV.txt"); do
  ssh "$host" "docker pull registry.example.com/orders:$ENV && docker restart orders" &
done
wait
echo "deployed $ENV"
