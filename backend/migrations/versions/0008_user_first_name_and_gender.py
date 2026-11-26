"""A first name and a gender on each account, asked at registration.

For the mobile app. Gender is one of `female`, `male` or `prefer_not_to_say`, stored as text with a CHECK, like every
other fixed choice in this schema. The name is stored trimmed, 1 to 50 characters.

Accounts made before this migration have neither, so both columns allow NULL. Registration always fills both.
Additive only: nothing is rewritten or removed.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN first_name text")
    op.execute("ALTER TABLE users ADD COLUMN gender text")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_first_name_not_blank CHECK (btrim(first_name) <> '')")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_first_name_length CHECK (char_length(first_name) <= 50)")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_gender_valid CHECK (gender IN ('female', 'male', 'prefer_not_to_say'))"
    )


def downgrade() -> None:
    # Dropping the columns drops their constraints with them.
    op.execute("ALTER TABLE users DROP COLUMN gender")
    op.execute("ALTER TABLE users DROP COLUMN first_name")
