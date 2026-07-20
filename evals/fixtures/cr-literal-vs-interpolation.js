"use strict";

/**
 * Builds the cache key for a badge request. The key MUST be unique per matched
 * route segment (`match[0]`) plus its stringified query params, so that
 * requests for DIFFERENT routes never collide on the same cache entry.
 */
function buildCacheKey(match, query) {
  const stringified = JSON.stringify(query || {});

  // BUG: the intended interpolation `${match[0]}` was written WITHOUT the
  // `${...}`, so the characters `match[0]` are emitted literally. `match` and
  // its value are never read here. The template below evaluates to the SAME
  // constant string "match[0]?<stringified>" for every route — e.g. both
  // /users and /orders produce "match[0]?{}" — so every request collides on
  // one cache entry and callers get another route's cached badge.
  const cacheKey = `match[0]?${stringified}`;

  return cacheKey;
}

function handleRequest(req, cache, match) {
  const key = buildCacheKey(match, req.query);
  if (cache.has(key)) {
    // Returns whatever was cached under the shared "match[0]?..." key —
    // possibly a completely different route's result.
    return cache.get(key);
  }
  const result = computeBadge(match, req.query);
  cache.set(key, result);
  return result;
}

function computeBadge(match, query) {
  return { label: match[0], query };
}

module.exports = { buildCacheKey, handleRequest };
