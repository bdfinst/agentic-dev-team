import { expect, test } from 'vitest';
import { applyDiscount } from '../../src/pricing.js';

test('discount', () => expect(applyDiscount(100, 'gold')).toBe(90));
