# migrate.py
import sqlite3
import psycopg2
import os

SQLITE_PATH = "aphp_jobs.db"
PG_URL      = os.getenv("DATABASE_URL")

def migrate():
    print("🔄 Migration SQLite → Supabase...")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn     = psycopg2.connect(PG_URL, sslmode="require")

    tables = ["jobs", "feedbacks", "pipeline_runs"]

    for table in tables:
        print(f"\n  📦 Migration table '{table}'...")
        try:
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            cols = [d[0] for d in sqlite_conn.execute(f"SELECT * FROM {table} LIMIT 0").description]

            if not rows:
                print(f"     ⚠️  Table vide")
                continue

            placeholders = ",".join(["%s"] * len(cols))
            cols_str     = ",".join(cols)

            with pg_conn.cursor() as cur:
                for row in rows:
                    cur.execute(f"""
                        INSERT INTO {table} ({cols_str})
                        VALUES ({placeholders})
                        ON CONFLICT (id) DO NOTHING
                    """, row)

            pg_conn.commit()
            print(f"     ✅ {len(rows)} lignes migrées")

        except Exception as e:
            print(f"     ❌ Erreur : {e}")

    sqlite_conn.close()
    pg_conn.close()
    print("\n✅ Migration terminée !")

if __name__ == "__main__":
    migrate()