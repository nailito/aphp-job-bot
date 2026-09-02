"""Shared, non-destructive PostgreSQL schema initialization."""

from pathlib import Path


def initialize_schema(connection) -> None:
    schema_path = Path(__file__).resolve().parent / "sql" / "schema.sql"
    statements = schema_path.read_text(encoding="utf-8").split(";")
    with connection.cursor() as cursor:
        for statement in statements:
            if statement.strip():
                cursor.execute(statement)
    connection.commit()
