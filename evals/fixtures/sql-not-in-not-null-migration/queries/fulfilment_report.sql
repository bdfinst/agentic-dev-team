-- Fulfilment dashboard queries.

-- Orders placed in the reporting window, newest first.
SELECT o.id, o.customer_id, o.status, o.placed_at
FROM orders AS o
WHERE o.placed_at >= :window_start
  AND o.placed_at < :window_end
ORDER BY o.placed_at DESC;

-- Shipments per carrier in the window.
SELECT s.carrier, COUNT(*) AS shipment_count
FROM shipments AS s
WHERE s.shipped_at >= :window_start
  AND s.shipped_at < :window_end
GROUP BY s.carrier;

-- Shipments still waiting for a tracking number.
SELECT s.id, s.order_id, s.carrier
FROM shipments AS s
WHERE s.tracking_no IS NULL;

-- Orders that were never shipped.
SELECT o.id, o.customer_id, o.placed_at
FROM orders AS o
WHERE o.cancelled_at IS NULL
  AND o.id NOT IN (SELECT s.order_id FROM shipments AS s);

-- Refunded amount per customer.
SELECT o.customer_id, SUM(r.amount) AS refunded
FROM refunds AS r
JOIN orders AS o ON o.id = r.order_id
GROUP BY o.customer_id;
