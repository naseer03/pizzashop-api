"""Idempotent DDL for ORM/schema drift (no Alembic in this repo)."""

from __future__ import annotations

import logging

from sqlalchemy import Engine, text

log = logging.getLogger("uvicorn.error")


def _has_column(conn, table: str, column: str) -> bool:
    q = text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
        """
    )
    n = conn.execute(q, {"t": table, "c": column}).scalar()
    return int(n or 0) > 0


def _order_status_type(conn) -> str | None:
    q = text(
        """
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'status'
        """
    )
    row = conn.execute(q).scalar()
    return str(row) if row is not None else None


def _menu_item_size_type(conn) -> str | None:
    q = text(
        """
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'menu_item_sizes' AND COLUMN_NAME = 'size_name'
        """
    )
    row = conn.execute(q).scalar()
    return str(row) if row is not None else None


def _order_item_size_type(conn) -> str | None:
    q = text(
        """
        SELECT COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'order_items' AND COLUMN_NAME = 'size'
        """
    )
    row = conn.execute(q).scalar()
    return str(row) if row is not None else None


def _has_fk(conn, table: str, fk_name: str) -> bool:
    q = text(
        """
        SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :t
          AND CONSTRAINT_NAME = :fk
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        """
    )
    n = conn.execute(q, {"t": table, "fk": fk_name}).scalar()
    return int(n or 0) > 0


def _has_table(conn, table: str) -> bool:
    q = text(
        """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
        """
    )
    n = conn.execute(q, {"t": table}).scalar()
    return int(n or 0) > 0


def _crusts_category_fk_constraint(conn, *, referenced_table: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'crusts'
              AND COLUMN_NAME = 'category_id' AND REFERENCED_TABLE_NAME = :ref
            LIMIT 1
            """
        ),
        {"ref": referenced_table},
    ).scalar()
    return str(row) if row else None


def apply_cashier_schema_patches(engine: Engine) -> None:
    """Add known missing columns/constraints for legacy DBs."""
    try:
        with engine.begin() as conn:
            if not _has_column(conn, "employees", "password_hash"):
                conn.execute(
                    text("ALTER TABLE employees ADD COLUMN password_hash VARCHAR(255) NULL")
                )
                log.warning("Applied DDL: employees.password_hash")

            col_type = _order_status_type(conn)
            if col_type and "on_hold" not in col_type:
                conn.execute(
                    text(
                        """
                        ALTER TABLE orders MODIFY COLUMN status ENUM(
                            'pending','on_hold','confirmed','preparing','ready',
                            'out_for_delivery','delivered','completed','cancelled'
                        ) NOT NULL DEFAULT 'pending'
                        """
                    )
                )
                log.warning("Applied DDL: orders.status extended with on_hold")

            menu_size_type = _menu_item_size_type(conn)
            if menu_size_type and "extra_large" not in menu_size_type:
                conn.execute(
                    text(
                        """
                        ALTER TABLE menu_item_sizes
                        MODIFY COLUMN size_name ENUM('small','medium','large','extra_large') NOT NULL
                        """
                    )
                )
                log.warning("Applied DDL: menu_item_sizes.size_name extended with extra_large")

            order_item_size_type = _order_item_size_type(conn)
            if order_item_size_type and "extra_large" not in order_item_size_type:
                conn.execute(
                    text(
                        """
                        ALTER TABLE order_items
                        MODIFY COLUMN size ENUM('small','medium','large','extra_large') NULL
                        """
                    )
                )
                log.warning("Applied DDL: order_items.size extended with extra_large")

            menu_size_type_half = _menu_item_size_type(conn)
            if menu_size_type_half and "half" not in menu_size_type_half:
                conn.execute(
                    text(
                        """
                        ALTER TABLE menu_item_sizes
                        MODIFY COLUMN size_name ENUM(
                            'half','small','medium','large','extra_large'
                        ) NOT NULL
                        """
                    )
                )
                log.warning("Applied DDL: menu_item_sizes.size_name extended with half")

            order_item_size_type_half = _order_item_size_type(conn)
            if order_item_size_type_half and "half" not in order_item_size_type_half:
                conn.execute(
                    text(
                        """
                        ALTER TABLE order_items
                        MODIFY COLUMN size ENUM(
                            'half','small','medium','large','extra_large'
                        ) NULL
                        """
                    )
                )
                log.warning("Applied DDL: order_items.size extended with half")

            if not _has_column(conn, "toppings", "category_id"):
                conn.execute(
                    text("ALTER TABLE toppings ADD COLUMN category_id INT NULL AFTER name")
                )
                # Backfill legacy topping rows to a valid category when possible.
                conn.execute(
                    text(
                        """
                        UPDATE toppings
                        SET category_id = (
                            SELECT id FROM categories ORDER BY id ASC LIMIT 1
                        )
                        WHERE category_id IS NULL
                        """
                    )
                )
                conn.execute(text("ALTER TABLE toppings MODIFY category_id INT NOT NULL"))
                log.warning("Applied DDL: toppings.category_id")

            if not _has_fk(conn, "toppings", "toppings_category_fk"):
                conn.execute(
                    text(
                        """
                        ALTER TABLE toppings
                        ADD CONSTRAINT toppings_category_fk
                        FOREIGN KEY (category_id) REFERENCES categories (id)
                        """
                    )
                )
                log.warning("Applied DDL: toppings.category_fk")

            if not _has_column(conn, "crusts", "category_id"):
                conn.execute(
                    text("ALTER TABLE crusts ADD COLUMN category_id INT NULL AFTER name")
                )
                log.warning("Applied DDL: crusts.category_id")

            fk_cc = _crusts_category_fk_constraint(conn, referenced_table="crust_categories")
            if fk_cc:
                safe_cn = fk_cc.replace("`", "")
                conn.execute(text(f"ALTER TABLE crusts DROP FOREIGN KEY `{safe_cn}`"))
                conn.execute(text("UPDATE crusts SET category_id = NULL"))
                log.warning(
                    "Applied DDL: dropped crusts FK to crust_categories; cleared crusts.category_id"
                )

            if _has_column(conn, "crusts", "category_id") and not _crusts_category_fk_constraint(
                conn, referenced_table="categories"
            ):
                conn.execute(
                    text(
                        """
                        UPDATE crusts c
                        LEFT JOIN categories cat ON cat.id = c.category_id
                        SET c.category_id = NULL
                        WHERE c.category_id IS NOT NULL AND cat.id IS NULL
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        ALTER TABLE crusts
                        ADD CONSTRAINT crusts_menu_category_fk
                        FOREIGN KEY (category_id) REFERENCES categories (id)
                        """
                    )
                )
                log.warning("Applied DDL: crusts.category_id FK -> categories")

            if not _has_table(conn, "topping_categories"):
                conn.execute(
                    text(
                        """
                        CREATE TABLE topping_categories (
                            topping_id INT NOT NULL,
                            category_id INT NOT NULL,
                            PRIMARY KEY (topping_id, category_id),
                            CONSTRAINT topping_categories_topping_fk
                                FOREIGN KEY (topping_id) REFERENCES toppings (id) ON DELETE CASCADE,
                            CONSTRAINT topping_categories_category_fk
                                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT IGNORE INTO topping_categories (topping_id, category_id)
                        SELECT id, category_id FROM toppings WHERE category_id IS NOT NULL
                        """
                    )
                )
                log.warning("Applied DDL: topping_categories")

            if not _has_table(conn, "crust_categories"):
                conn.execute(
                    text(
                        """
                        CREATE TABLE crust_categories (
                            crust_id INT NOT NULL,
                            category_id INT NOT NULL,
                            PRIMARY KEY (crust_id, category_id),
                            CONSTRAINT crust_categories_crust_fk
                                FOREIGN KEY (crust_id) REFERENCES crusts (id) ON DELETE CASCADE,
                            CONSTRAINT crust_categories_category_fk
                                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT IGNORE INTO crust_categories (crust_id, category_id)
                        SELECT id, category_id FROM crusts WHERE category_id IS NOT NULL
                        """
                    )
                )
                log.warning("Applied DDL: crust_categories")
            elif _has_column(conn, "crusts", "category_id"):
                conn.execute(
                    text(
                        """
                        INSERT IGNORE INTO crust_categories (crust_id, category_id)
                        SELECT id, category_id FROM crusts WHERE category_id IS NOT NULL
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT IGNORE INTO topping_categories (topping_id, category_id)
                        SELECT id, category_id FROM toppings WHERE category_id IS NOT NULL
                        """
                    )
                )

            if not _has_column(conn, "orders", "kot_printed"):
                conn.execute(
                    text(
                        "ALTER TABLE orders ADD COLUMN kot_printed BOOL NOT NULL DEFAULT FALSE AFTER payment_status"
                    )
                )
                log.warning("Applied DDL: orders.kot_printed")
    except Exception:
        log.exception("Cashier schema patch failed (check DB user has ALTER privileges)")
        raise
