# 2. Version the public API in the URL path

Date: 2024-11-05

## Status

Accepted

## Context

Partners integrate against our REST API and upgrade on their own schedule.

## Decision

Public endpoints carry the major version in the path (`/v1/...`). A new major
version runs side by side with the old one.

## Consequences

Old versions must be retired deliberately, with notice to partners.
