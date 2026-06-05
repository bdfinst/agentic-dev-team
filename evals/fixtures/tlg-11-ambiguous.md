# Behavior to design tests for

The "Apply filter" control on the product listing updates the results to match
the selected filters.

The description does **not** say whether applying a filter is a client-side
dynamic update (re-rendering results in place without a reload) or a full
server-side round-trip that reloads the page. Whether a browser-level dynamic
gate applies is genuinely unclear from this description alone.
