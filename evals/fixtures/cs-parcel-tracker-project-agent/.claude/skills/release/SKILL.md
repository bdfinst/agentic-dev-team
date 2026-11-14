---
name: release
description: Cut a release of Parcel Tracker - run checks, bump the version, and tag it.
---

# Release

1. Run `npm run lint` and `npm test`; stop on any failure.
2. Run `npm run build`.
3. Run `npm version minor` (or `patch` for fix-only releases).
4. Push the commit and tag: `git push --follow-tags`.
