"""
Apply cashier-related DB changes idempotently (no Alembic in this repo).

Usage (from project root):
  python scripts/ensure_cashier_schema.py

Same logic as API startup (see app.core.schema_patches).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.schema_patches import apply_cashier_schema_patches
from app.database import engine


def main() -> None:
    apply_cashier_schema_patches(engine)
    print("Done.")


if __name__ == "__main__":
    main()
