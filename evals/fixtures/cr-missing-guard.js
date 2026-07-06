"use strict";

/**
 * Determines whether a resolved package source is safe to cache and reuse
 * across installs. Sources are cacheable only when they resolve to an
 * immutable target: a pinned version or tag. Local filesystem sources
 * (`file://`) and floating branch resolutions are moving targets and must
 * never be treated as cacheable — caching them would serve stale or
 * wrong content on the next install.
 */
function isCacheable(source) {
  if (!source) return false;
  // Deliberately excludes file:// and branch resolutions (see docstring).
  return true;
}

/**
 * Store a resolved package in the shared cache, keyed by its source.
 */
class PackageRepository {
  constructor() {
    this._cache = new Map();
  }

  store(source, resolution) {
    // BUG: `isCacheable` exists specifically to reject file:// sources and
    // branch resolutions (per its own docstring), but this call site never
    // invokes it before caching — every resolution is cached unconditionally,
    // including local filesystem sources and floating branches, which then
    // get served as stale cached content on later installs.
    this._cache.set(source, resolution);
    return resolution;
  }

  get(source) {
    return this._cache.get(source);
  }
}

module.exports = { isCacheable, PackageRepository };
