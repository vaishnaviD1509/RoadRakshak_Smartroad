"""Tiny schema upgrade for databases created by an older version of the app.

db.create_all() creates missing tables (such as "teams") but never adds a new
column to a table that already exists. This adds the columns introduced later,
so an existing database/road_rakshak.db keeps working without being deleted.
"""
from sqlalchemy import inspect, text


def upgrade_schema(engine) -> list:
    """Add any missing columns. Returns a list of what was added."""
    added = []
    inspector = inspect(engine)

    if "complaints" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("complaints")}
        if "priority" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE complaints ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'Normal'"
                ))
            added.append("complaints.priority")

    return added