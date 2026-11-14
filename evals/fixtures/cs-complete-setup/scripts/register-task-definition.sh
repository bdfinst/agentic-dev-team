#!/usr/bin/env bash
# Usage: register-task-definition.sh <image-uri>
# Registers a new revision of the service's task definition that runs <image-uri>
# and prints the new task definition ARN.
set -euo pipefail

image="$1"
current=$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].taskDefinition' --output text)

aws ecs describe-task-definition --task-definition "$current" --query taskDefinition \
  | jq --arg image "$image" '.containerDefinitions[0].image = $image
      | {family, containerDefinitions, taskRoleArn, executionRoleArn, networkMode,
         requiresCompatibilities, cpu, memory}' \
  > /tmp/task-definition.json

aws ecs register-task-definition --cli-input-json file:///tmp/task-definition.json \
  --query 'taskDefinition.taskDefinitionArn' --output text
