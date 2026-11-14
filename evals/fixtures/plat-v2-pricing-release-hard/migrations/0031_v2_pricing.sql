-- Ships with v2 pricing.
ALTER TABLE price_rules ADD COLUMN tier_multiplier numeric NOT NULL DEFAULT 1.0;
UPDATE price_rules SET tier_multiplier = legacy_discount_pct / 100.0 + 1.0;
ALTER TABLE price_rules DROP COLUMN legacy_discount_pct;
