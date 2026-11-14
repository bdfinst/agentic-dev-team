# orders service

- 6 production hosts behind a load balancer that health-checks `GET /healthz`.
- Last month's release 2.2 broke checkout for 25 minutes. Rolling back took
  that long because we rebuilt the 2.1 image from the old commit by hand.
- Release 2.3 (next week) includes migration 0019.
