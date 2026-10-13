from sqlalchemy import Connection, text


class SqlVendorRepository:
    """Vendors are per user. Names match ignoring case and surrounding spaces."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def find_by_name(self, name: str) -> int | None:
        return self._conn.execute(
            text("SELECT id FROM vendors WHERE lower(btrim(name)) = lower(btrim(:name))"), {"name": name}
        ).scalar_one_or_none()

    def find_or_create(self, name: str) -> int:
        existing_id = self.find_by_name(name)
        if existing_id is not None:
            return existing_id
        return self._conn.execute(
            text("INSERT INTO vendors (user_id, name) VALUES (app_user_id(), btrim(:name)) RETURNING id"),
            {"name": name},
        ).scalar_one()
