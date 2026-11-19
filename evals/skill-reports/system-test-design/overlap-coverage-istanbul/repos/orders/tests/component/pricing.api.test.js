import { expect, test } from 'vitest';
import { post } from './client.js';

test('discount', async () => expect((await post('/price', { total: 100, tier: 'gold' })).total).toBe(90));
