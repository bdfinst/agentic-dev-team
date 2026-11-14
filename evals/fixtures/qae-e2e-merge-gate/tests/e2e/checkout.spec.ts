import { test, expect } from '@playwright/test';

test('order total includes tax', async ({ page }) => {
  await page.goto('http://localhost:3000/cart');
  await page.click('text=Checkout');
  await page.waitForTimeout(5000); // wait for tax-service
  await expect(page.locator('#total')).toHaveText('$108.25');
});

test('out-of-stock item cannot be added', async ({ page }) => {
  await page.goto('http://localhost:3000/products/sku-991');
  await expect(page.locator('button.add')).toBeDisabled();
});
