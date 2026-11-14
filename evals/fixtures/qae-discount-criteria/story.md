# Story: Loyalty discount at checkout

As a loyalty member, I want my discount applied at checkout so that I pay less.

## Acceptance criteria (draft from refinement)

1. The discount applies correctly.
2. Gold members get a bigger discount.
3. It works with coupons.

## Business rules (from the product owner's notes)

- Silver members: 5% off the order subtotal.
- Gold members: 10% off the order subtotal.
- The loyalty discount applies only when the subtotal is $100.00 or more.
- A coupon is applied first; the loyalty discount is then computed on the
  post-coupon subtotal, and the $100.00 threshold is checked against the
  post-coupon subtotal.
- Shipping is never discounted.
- Members whose membership expired are treated as non-members.
