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
    except Exception:
        log.exception("Cashier schema patch failed (check DB user has ALTER privileges)")
        raise
