# Behavior to design tests for

When the user clicks "Add to cart" on a product, the cart badge in the page
header updates to show the new item count without a full page reload.

The user performs an action and must *see* the correctly rendered result (the
updated badge) in the browser. The flow runs through the front end, an API call,
and a re-render of the header.
