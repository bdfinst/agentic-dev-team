-- Orders with at least one item.
SELECT DISTINCT o.id FROM orders o JOIN order_items i ON i.order_id = o.id;
