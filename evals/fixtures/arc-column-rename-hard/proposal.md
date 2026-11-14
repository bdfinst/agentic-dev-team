# Proposal: rename customers.phone to phone_number

We want E.164-normalized numbers under a clearer name. Plan: ship migration
0042 with Friday's crm release, and update `crm/customers.py` to use
`phone_number` in the same release. support will pick up the new name in its
next release the following Wednesday.
