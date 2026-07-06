"use strict";

/**
 * Builds the cache key for a badge request. The key MUST be unique per
 * matched route segment (`match[0]`) plus its stringified query params,
 * so that requests for different routes never collide on the same cache
 * entry.
 */
function buildCacheKey(match, query) {
  const stringified = JSON.stringify(query || {});

  // BUG: `match[0]` is written as a literal `match[0]` character sequence
  // instead of being interpolated. Every request produces the exact same
  // cache key string "match[0]?<stringified>" regardless of which route
  // actually matched, so unrelated requests collide on one cache entry.
  const cacheKey = `match[0]?${stringified}`;

  return cacheKey;
}

function handleRequest(req, cache, match) {
  const key = buildCacheKey(match, req.query);
  if (cache.has(key)) {
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
