# Behavior to design tests for

On the cart page, changing an item's quantity fires an **HTMX** `POST /cart/item`.
The server writes the new quantity to the database, then returns an HTML fragment
that HTMX swaps into the order-total element (`hx-target="#order-total"`,
`hx-swap="outerHTML"`).

The behavior spans a server-side state mutation **and** a client-side swap of the
returned fragment into the DOM.
