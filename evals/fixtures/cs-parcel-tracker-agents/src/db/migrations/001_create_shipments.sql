CREATE TABLE shipments (
  id BIGSERIAL PRIMARY KEY,
  carrier TEXT NOT NULL,
  tracking_number TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
