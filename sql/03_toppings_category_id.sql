-- Align legacy `toppings` tables with the current API model (column: category_id -> categories.id).
-- Run only if: SHOW COLUMNS FROM toppings LIKE 'category_id'; returns nothing.

ALTER TABLE toppings
  ADD COLUMN category_id INT NULL AFTER name;

-- Point all existing rows at a valid category (pick the lowest id; change if needed).
UPDATE toppings t
  SET category_id = (SELECT id FROM categories c ORDER BY c.id ASC LIMIT 1)
  WHERE t.category_id IS NULL;

ALTER TABLE toppings
  MODIFY category_id INT NOT NULL;

ALTER TABLE toppings
  ADD CONSTRAINT toppings_category_fk FOREIGN KEY (category_id) REFERENCES categories (id);
