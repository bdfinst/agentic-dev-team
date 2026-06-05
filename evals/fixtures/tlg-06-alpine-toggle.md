# Behavior to design tests for

A product card has a "Show details" control wired with **Alpine.js**
(`x-data="{ open: false }"`, `@click="open = !open"`, `x-show="open"`). Clicking
it toggles a details panel's visibility entirely on the client.

There is **no server call** — the behavior is a purely client-side dynamic swap
of what the user sees.
