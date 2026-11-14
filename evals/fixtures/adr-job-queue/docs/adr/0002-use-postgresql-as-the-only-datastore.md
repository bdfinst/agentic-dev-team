# 2. Use PostgreSQL as the only datastore

Date: 2025-02-03

## Status

Accepted

## Context

The team is four engineers with no dedicated operations staff. Each new
stateful service adds backups, upgrades, and on-call load.

## Decision

All persistent state lives in the single managed PostgreSQL 16 instance.
We add another datastore only when PostgreSQL demonstrably cannot meet a need.

## Consequences

One backup and restore procedure. Some workloads (search, queues) run on
PostgreSQL features instead of purpose-built systems.
