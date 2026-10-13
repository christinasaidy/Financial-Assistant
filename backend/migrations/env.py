"""Alembic environment.

Migrations are written by hand as SQL (see versions/), because autogenerate cannot express the
CHECK constraints, triggers and row-level security policies this project relies on. They run as
the table-owning `expense_owner` role, never as the runtime `app_user` role.
"""

from alembic import context
from sqlalchemy import create_engine, pool

from app.infrastructure.config import Settings

config = context.config


def _migration_url() -> str:
    url = Settings().migration_database_url
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is not set (see backend/.env.example)")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_migration_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_migration_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
