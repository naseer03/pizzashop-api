-- Many-to-many links between toppings/crusts and menu categories.
-- Safe to run multiple times (INSERT IGNORE).

CREATE TABLE IF NOT EXISTS topping_categories (
    topping_id INT NOT NULL,
    category_id INT NOT NULL,
    PRIMARY KEY (topping_id, category_id),
    CONSTRAINT topping_categories_topping_fk
        FOREIGN KEY (topping_id) REFERENCES toppings (id) ON DELETE CASCADE,
    CONSTRAINT topping_categories_category_fk
        FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crust_categories (
    crust_id INT NOT NULL,
    category_id INT NOT NULL,
    PRIMARY KEY (crust_id, category_id),
    CONSTRAINT crust_categories_crust_fk
        FOREIGN KEY (crust_id) REFERENCES crusts (id) ON DELETE CASCADE,
    CONSTRAINT crust_categories_category_fk
        FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
);

INSERT IGNORE INTO topping_categories (topping_id, category_id)
SELECT id, category_id FROM toppings WHERE category_id IS NOT NULL;

INSERT IGNORE INTO crust_categories (crust_id, category_id)
SELECT id, category_id FROM crusts WHERE category_id IS NOT NULL;
