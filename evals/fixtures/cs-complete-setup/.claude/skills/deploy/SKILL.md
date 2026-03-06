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

## Steps

### 1. Run pre-deploy checks

Run `npm test` and `npm run lint`. Abort if either fails.

### 2. Build artifacts

Run `npm run build`. Verify the `dist/` directory is created.

### 3. Build Docker image

Run `docker build -t app:$(git rev-parse --short HEAD) .`

### 4. Push to registry

Run `docker push $ECR_REPO:$(git rev-parse --short HEAD)`

### 5. Update service

Run `aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment`

### 6. Smoke test

Hit the `/health` endpoint. If it returns non-200 after 60 seconds, trigger rollback.

### 7. Report

Print deployment status: image tag, environment, timestamp, health check result.
