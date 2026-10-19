from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _scalar_default_sql(column) -> str | None:
    """SQL literal for a column's Python-side scalar default (used to backfill old rows)."""
    if column.default is not None and getattr(column.default, "is_scalar", False):
        value = column.default.arg
        return str(int(value)) if isinstance(value, bool) else repr(value)
    return None


def _rebuild_table(conn, table: Table) -> None:
    """SQLite can't ALTER a column's NOT NULL away, so recreate the table with the current
    schema and copy the rows across. Columns the old table lacks get their default."""
    inspector = inspect(conn)
    old_columns = {c["name"] for c in inspector.get_columns(table.name)}
    old_name = f"{table.name}__old"

    for index in inspector.get_indexes(table.name):  # index names are global in SQLite
        conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
    conn.execute(text(f'ALTER TABLE "{table.name}" RENAME TO "{old_name}"'))
    table.create(conn)

    targets, values = [], []
    for column in table.columns:
        targets.append(f'"{column.name}"')
        if column.name in old_columns:
            values.append(f'"{column.name}"')
        else:
            values.append(_scalar_default_sql(column) or "NULL")
    conn.execute(text(f'INSERT INTO "{table.name}" ({", ".join(targets)}) SELECT {", ".join(values)} FROM "{old_name}"'))
    conn.execute(text(f'DROP TABLE "{old_name}"'))


def _migrate_schema() -> None:
    """Bring a database created by an earlier version of the app up to the current models.

    create_all() only creates missing *tables*. Anyone upgrading with an existing database would
    otherwise hit "no such column" (new columns) or "NOT NULL constraint failed" (a column that
    used to be required and now isn't). Nothing is dropped; existing rows are kept."""
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"]: c for c in inspector.get_columns(table.name)}

            loosened = [
                c.name for c in table.columns
                if c.name in existing and c.nullable and not existing[c.name]["nullable"] and not c.primary_key
            ]
            if loosened and engine.dialect.name == "sqlite":
                _rebuild_table(conn, table)
                continue

            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                default = _scalar_default_sql(column)
                clause = f" DEFAULT {default}" if default is not None else ""
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{clause}'))
            for index in table.indexes:  # ADD COLUMN doesn't create the column's index
                index.create(conn, checkfirst=True)


def init_db() -> None:
    # Importing models here (rather than at module load) avoids circular imports while still
    # registering every table on Base.metadata before create_all runs.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
