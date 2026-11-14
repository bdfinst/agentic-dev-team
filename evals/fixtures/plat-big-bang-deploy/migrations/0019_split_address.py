"""Release 2.3: move the free-text address into structured columns."""


def upgrade(db):
    db.execute("ALTER TABLE orders ADD COLUMN street text, ADD COLUMN city text")
    db.execute("UPDATE orders SET street = split_part(address, ',', 1), "
               "city = split_part(address, ',', 2)")
    db.execute("ALTER TABLE orders DROP COLUMN address")
