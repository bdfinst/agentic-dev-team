from support.db import query


def find_by_phone(phone):
    return query("SELECT id, name FROM customers WHERE phone = %s", phone)
