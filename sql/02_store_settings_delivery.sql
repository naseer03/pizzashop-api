-- Run once if store_settings already existed without these columns (ignore errors if already applied).
ALTER TABLE store_settings ADD COLUMN delivery_fee DECIMAL(10, 2) NOT NULL DEFAULT 3.99;
ALTER TABLE store_settings ADD COLUMN min_order_for_free_delivery DECIMAL(10, 2) NOT NULL DEFAULT 0.00;
