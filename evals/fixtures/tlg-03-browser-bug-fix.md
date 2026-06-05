# Behavior to design tests for

Bug fix. A logged-in user reported, **while using the app in the browser**, that
the order discount shown at checkout is wrong: a 10%-off coupon applied to a $200
order displays a $10 discount instead of $20.

Reproduce the defect and add a regression test so it cannot recur. The bug was
discovered in the browser at the checkout page.
