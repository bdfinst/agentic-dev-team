# Object Calisthenics

Nine rules for writing clean, maintainable, testable object-oriented code. Apply to **business domain code** — exempt DTOs, config classes, test builders, and framework boilerplate.

Source: Jeff Bay, "Object Calisthenics" (*The ThoughtWorks Anthology*, Pragmatic Bookshelf, 2008)

---

## The Rules

### 1. One Level of Indentation Per Method

If a method has nested `if`/`for`/`while`, extract the inner block into a named method.

```
// BAD
function processPayments(payments) {
  for payment in payments:
    if payment.isEligible:
      if payment.amount > 0:
        submit(payment)
}

// GOOD
function processPayments(payments) {
  for payment in payments:
    processIfEligible(payment)
}
```

### 2. Don't Use the ELSE Keyword

Replace `if/else` with guard clauses (early returns) or polymorphism.

```
// BAD
function calculateShipping(method):
  if method == "express": return weight * 2.5
  else if method == "overnight": return 25.0
  else: return 0

// GOOD — guard clauses
function calculateShipping(method):
  if method == "express": return weight * 2.5
  if method == "overnight": return 25.0
  return 0
```

### 3. Wrap All Primitives and Strings

Domain-meaningful primitives become value objects with validation.

```
// BAD
createOrder(customerId: string, amount: decimal, email: string)

// GOOD
createOrder(customerId: CustomerId, amount: Money, email: EmailAddress)
```

### 4. First-Class Collections

Any class with a collection field should contain no other fields. The collection gets its own class with domain behavior.

```
// BAD
class BatchProcessor:
  payments: List<Payment>
  batchId: string   // mixing concerns

// GOOD
class PaymentBatch:
  payments: List<Payment>   // the ONLY field
  total(): Money
  eligiblePayments(): List<Payment>
```

### 5. One Dot Per Line (Law of Demeter)

Don't chain through object graphs. Each method call should be on the immediate collaborator.

```
// BAD — reaching through the graph
city = order.customer.address.city

// GOOD — ask the immediate object
city = order.shippingCity   // Order delegates to its own data
```

### 6. Don't Abbreviate

Names should be intention-revealing. If a name is too long, the class may have too many responsibilities.

```
// BAD
proc = new Proc()
txn = getTxn(id)
amt = calcAmt(txn)

// GOOD
processor = new PaymentProcessor()
transaction = getTransaction(id)
amount = calculateAmount(transaction)
```

### 7. Keep All Entities Small

- Classes: under 200 lines
- Methods: under 20 lines
- Packages/modules: under 15 classes

If a class exceeds these limits, it likely violates SRP — extract responsibilities.

### 8. No Classes with More Than Two Instance Variables

The spirit: classes should be small and focused. In practice, aim for fewer than five fields. More than five is a strong signal for Extract Class.

### 9. No Getters/Setters/Properties (Tell, Don't Ask)

Move behavior into the object that owns the data instead of exposing data for others to operate on.

```
// BAD — asking for data, deciding externally
if account.balance >= amount:
  account.balance -= amount

// GOOD — telling the object what to do
account.withdraw(amount)   // Account enforces its own invariants
```

---

## Applying Pragmatically

These are training exercises, not absolute laws. Use them as design pressure:

| Rule | Always Apply | Pragmatic Exceptions |
|---|---|---|
| One indentation level | Yes | Complex LINQ / stream expressions |
| No ELSE | Yes | Simple boolean returns |
| Wrap primitives | For domain values | Infrastructure code, DTOs |
| First-class collections | When collection has behavior | Simple DTOs |
| One dot per line | At domain boundaries | Fluent APIs, builders |
| Don't abbreviate | Yes | Industry-standard acronyms (HTTP, SQL, ID, JWT) |
| Small classes | Yes | EF/ORM configurations, test fixtures |
| Few instance variables | As design pressure | Aggregate roots may need more |
| No getters | At domain boundaries | DTOs, serialization, view models |
