---
name: deploy
description: Deploy the application to staging or production.
argument-hint: "[staging | production]"
user-invocable: true
---

# Deploy

## Parse Arguments

Arguments: $ARGUMENTS

- `staging` (default): deploy to staging environment
- `production`: deploy to production (requires staging green)

## Environment

Each environment has its own values for these variables, set in the shell before the skill runs:

- `ECR_REPO`: the ECR repository URI for the image
- `CLUSTER`: the ECS cluster name
- `SERVICE`: the ECS service name
- `STAGING_URL`: the staging base URL, used by the production gate
- `APP_URL`: the base URL of the target environment, used by the smoke test

## Steps

### 1. Run pre-deploy checks

Run `npm test` and `npm run lint`. Abort if either fails.

For `production` only: run `curl -fsS $STAGING_URL/health`. Abort if it does not return 200, because production requires a green staging deployment.

### 2. Build artifacts

Run `npm run build`. Verify the `dist/` directory is created.

### 3. Build Docker image

Run `docker build -t app:$(git rev-parse --short HEAD) .`

### 4. Push to registry

Run `docker tag app:$(git rev-parse --short HEAD) $ECR_REPO:$(git rev-parse --short HEAD)`,
then `docker push $ECR_REPO:$(git rev-parse --short HEAD)`

### 5. Update service

Run `aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment`

### 6. Smoke test

Request `$APP_URL/health`. If it returns non-200 after 60 seconds, trigger rollback.

### 7. Report

Print deployment status: image tag, environment, timestamp, health check result.
