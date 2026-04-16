-- Run against existing DBs created before delivery / free-delivery settings were added.
ALTER TABLE store_settings
  ADD COLUMN delivery_fee DECIMAL(10, 2) NOT NULL DEFAULT 3.99 AFTER tax_rate,
  ADD COLUMN free_delivery_minimum_order DECIMAL(10, 2) NOT NULL DEFAULT 0.00 AFTER delivery_fee;
