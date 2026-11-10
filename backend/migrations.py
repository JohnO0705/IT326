"""Add the new fields to a first-version database without dropping tables."""

from sqlalchemy import Column, inspect, text
from sqlalchemy.schema import CreateColumn

from backend.orm_mapping import metadata


def missing_columns(engine) -> dict:
    inspector = inspect(engine)
    result = {}
    for table in metadata.sorted_tables:
        if inspector.has_table(table.name):
            existing = {c["name"].lower() for c in inspector.get_columns(table.name)}
            missing = [c for c in table.columns if c.name not in existing]
            if missing:
                result[table.name] = missing
    return result


def upgrade_columns(engine) -> list[str]:
    missing = missing_columns(engine)
    if not missing:
        return []
    with engine.begin() as connection:
        for table, columns in missing.items():
            for column in columns:
                # Legacy rows are filled below before the application reads them.
                addition = Column(column.name, column.type, nullable=True)
                ddl = str(CreateColumn(addition).compile(dialect=engine.dialect))
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD {ddl}")
        if "tb_subtasks" in missing:
            connection.execute(text(
                "UPDATE tb_subtasks SET user_id = "
                "(SELECT user_id FROM tb_tasks WHERE tb_tasks.task_id = tb_subtasks.task_id) "
                "WHERE user_id IS NULL"
            ))
            for name in ("is_pinned", "is_hidden", "is_deleted"):
                connection.execute(text(f"UPDATE tb_subtasks SET {name} = 0 WHERE {name} IS NULL"))
            for name in ("created_at", "updated_at"):
                connection.execute(text(
                    f"UPDATE tb_subtasks SET {name} = "
                    f"(SELECT {name} FROM tb_tasks WHERE tb_tasks.task_id = tb_subtasks.task_id) "
                    f"WHERE {name} IS NULL"
                ))
        if "tb_reminders" in missing:
            connection.execute(text(
                "UPDATE tb_reminders SET sent_at = reminder_date "
                "WHERE is_sent = 1 AND sent_at IS NULL"
            ))
    return [f"Updated {table}: " + ", ".join(c.name for c in columns)
            for table, columns in missing.items()]
