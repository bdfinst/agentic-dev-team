# Behavior to design tests for

Bug fix that is **also** user-facing dynamic behavior. A user reported, **in the
browser**, that after applying a coupon code the displayed order total does not
update — they must reload the page to see the discounted total. The total is
meant to update live when the coupon is applied.

Two signals are present at once: it is a **browser-discovered bug fix** and a
**user-facing dynamic** behavior (the user acts and must see the total re-render).
