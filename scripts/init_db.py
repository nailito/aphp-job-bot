"""Create or update the PostgreSQL schema required by the application."""

import os

import psycopg

from database_schema import initialize_schema


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    try:
        with psycopg.connect(database_url) as connection:
            initialize_schema(connection)
    except Exception as error:
        raise SystemExit(f"Database initialization failed: {type(error).__name__}") from None

    print("Database schema is ready.")


if __name__ == "__main__":
    main()
