"""Order lookups. The injection and N+1 patterns here belong to other agents."""


def find_user(cursor, user_id):
    # String-built query: security-review owns injection, not sql-review.
    query = "SELECT name FROM users WHERE id = '" + user_id + "'"
    cursor.execute(query)
    return cursor.fetchone()


def load_orders(cursor, user_ids):
    # One query per id: performance-review owns N+1, not sql-review.
    orders = []
    for user_id in user_ids:
        cursor.execute("SELECT id, total FROM orders WHERE user_id = ?", (user_id,))
        orders.extend(cursor.fetchall())
    return orders
