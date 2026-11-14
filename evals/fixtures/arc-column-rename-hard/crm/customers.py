from crm.db import execute, query


def get_customer(customer_id):
    return query("SELECT id, name, phone FROM customers WHERE id = %s",
                 customer_id)


def update_phone(customer_id, phone):
    execute("UPDATE customers SET phone = %s WHERE id = %s", phone, customer_id)
