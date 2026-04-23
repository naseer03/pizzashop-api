-- Cashier POS / API alignment (run against your Pizza Shop database).
-- Safe to re-run: employees line may error once if column already exists (ignore 1060).

ALTER TABLE employees
  ADD COLUMN password_hash VARCHAR(255) NULL
  COMMENT 'PBKDF2 hash for cashier POS login; NULL until set by admin';

-- Kitchen hold workflow: extend order status enum (adjust if your ENUM list differs).
ALTER TABLE orders
  MODIFY COLUMN status ENUM(
    'pending',
    'on_hold',
    'confirmed',
    'preparing',
    'ready',
    'out_for_delivery',
    'delivered',
    'completed',
    'cancelled'
  ) NOT NULL DEFAULT 'pending';
