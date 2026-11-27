from collections.abc import Sequence

from sqlalchemy import Connection, text

from app.domain.assistant.names import KnownName, NameKind
from app.domain.assistant.prompt import VIEW_CATEGORIES

# Each kind as the assistant views spell it, from confirmed receipts only (the views show nothing else), with how
# many receipts use the name and when it was last used. Row-level security keeps it to the user's own rows.
_INVENTORY = {
    NameKind.VENDOR: """
        SELECT v.name, count(DISTINCT r.id) AS receipts, max(r.receipt_date) AS last_used
        FROM vendors v JOIN receipts r ON r.vendor_id = v.id AND r.status = 'confirmed'
        GROUP BY v.name
    """,
    NameKind.ITEM: """
        SELECT ri.normalized_name AS name, count(DISTINCT r.id) AS receipts, max(r.receipt_date) AS last_used
        FROM receipt_items ri JOIN receipts r ON r.id = ri.receipt_id AND r.status = 'confirmed'
        WHERE ri.normalized_name IS NOT NULL
        GROUP BY ri.normalized_name
    """,
    # Every category the user has, used or not, as the views name them (an item without one is 'Uncategorized').
    NameKind.CATEGORY: """
        SELECT c.name, count(DISTINCT r.id) AS receipts, max(r.receipt_date) AS last_used
        FROM categories c
        LEFT JOIN receipts r ON r.status = 'confirmed' AND (r.primary_category_id = c.id OR EXISTS (
            SELECT 1 FROM receipt_items ri WHERE ri.receipt_id = r.id AND ri.category_id = c.id))
        GROUP BY c.name
    """,
}

# The brands printed on the user's items ("TEREA Oasis" is saved as the item tobacco, brand terea).
_BRANDS = """
    SELECT ri.brand AS name, count(DISTINCT r.id) AS receipts, max(r.receipt_date) AS last_used
    FROM receipt_items ri JOIN receipts r ON r.id = ri.receipt_id AND r.status = 'confirmed'
    WHERE ri.brand IS NOT NULL
    GROUP BY ri.brand
"""


class SqlNameRepository:
    """The user's vendor, item and category names over all their confirmed receipts (the Standard mode's lookups)."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def existing(self, kind: NameKind, names: Sequence[str]) -> set[str]:
        if not names:
            return set()
        wanted = list(dict.fromkeys(names))
        found = set(
            self._conn.execute(
                text(f"SELECT name FROM ({_INVENTORY[kind]}) known WHERE name = ANY(:names)"), {"names": wanted}
            ).scalars()
        )
        if kind is NameKind.CATEGORY:
            found |= {name for name in wanted if name in VIEW_CATEGORIES}
        return found

    def inventory(self, kind: NameKind, limit: int) -> list[KnownName]:
        known = self._newest_first(_INVENTORY[kind], limit)
        if kind is NameKind.CATEGORY:
            known += [KnownName(name, 0, None) for name in VIEW_CATEGORIES if name not in {k.name for k in known}]
        return known

    def brands(self, limit: int) -> list[KnownName]:
        return self._newest_first(_BRANDS, limit)

    def _newest_first(self, names_sql: str, limit: int) -> list[KnownName]:
        rows = self._conn.execute(
            text(f"SELECT * FROM ({names_sql}) known ORDER BY last_used DESC NULLS LAST, name LIMIT :limit"),
            {"limit": limit},
        ).all()
        return [KnownName(row.name, row.receipts, row.last_used) for row in rows]
