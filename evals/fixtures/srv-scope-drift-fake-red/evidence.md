# Verification evidence — Step 1.1

## RED (falsification: implementation stubbed out by moving `src/checkout/discount.ts` aside)

```
$ npx vitest run test/discount.test.ts
 FAIL  test/discount.test.ts [ test/discount.test.ts ]
Error: Cannot find module '../src/checkout/discount' imported from test/discount.test.ts
 Test Files  1 failed (1)
      Tests  no tests
```

## GREEN

```
$ npx vitest run test/discount.test.ts
 ✓ test/discount.test.ts (2 tests) 4ms
 Test Files  1 passed (1)
      Tests  2 passed (2)
```

## Suite

```
$ npx vitest run
 Test Files  41 passed (41)
      Tests  312 passed (312)
```
