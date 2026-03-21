import sqlite3
from datetime import datetime

DB_PATH = "aphp_jobs.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                TEXT PRIMARY KEY,
                title             TEXT,
                metier            TEXT,
                filiere           TEXT,
                hopital           TEXT,
                location          TEXT,
                contrat           TEXT,
                teletravail       TEXT,
                horaire           TEXT,
                temps_travail     TEXT,
                date_publication  TEXT,
                description       TEXT,
                url               TEXT,
                score             INTEGER DEFAULT NULL,
                mots_cles_matches TEXT DEFAULT NULL,
                raison            TEXT DEFAULT NULL,
                first_seen        TEXT,
                last_seen         TEXT,
                status            TEXT DEFAULT 'active'
            )
        """)
        conn.commit()
    print("✅ Base de données initialisée")

def upsert_jobs(jobs: list[dict]) -> dict:
    now = datetime.now().isoformat()

    with get_connection() as conn:
        site_ids     = {j["id"] for j in jobs}
        existing_ids = {row[0] for row in conn.execute("SELECT id FROM jobs WHERE status = 'active'")}
        new_ids      = site_ids - existing_ids
        removed_ids  = existing_ids - site_ids
        new_jobs     = [j for j in jobs if j["id"] in new_ids]

        for job in new_jobs:
            conn.execute("""
                INSERT OR IGNORE INTO jobs (
                    id, title, metier, filiere, hopital, location,
                    contrat, teletravail, horaire, temps_travail,
                    date_publication, description, url,
                    first_seen, last_seen, status
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, 'active'
                )
            """, (
                job.get("id", ""),
                job.get("title", ""),
                job.get("metier", ""),
                job.get("filiere", ""),
                job.get("hopital", ""),
                job.get("location", ""),
                job.get("contrat", ""),
                job.get("teletravail", ""),
                job.get("horaire", ""),
                job.get("temps_travail", ""),
                job.get("date_publication", ""),
                job.get("description", ""),
                job.get("url", ""),
                now,
                now,
            ))

        for job in jobs:
            if job["id"] in existing_ids:
                conn.execute(
                    "UPDATE jobs SET last_seen = ? WHERE id = ?",
                    (now, job["id"])
                )

        for job_id in removed_ids:
            conn.execute(
                "UPDATE jobs SET status = 'removed' WHERE id = ?",
                (job_id,)
            )

        conn.commit()

    print(f"  🆕 {len(new_jobs)} nouvelles offres")
    print(f"  🗑️  {len(removed_ids)} offres retirées")
    print(f"  ♻️  {len(existing_ids & site_ids)} offres déjà connues (ignorées)")

    return {"new": new_jobs, "removed": list(removed_ids)}

def save_scores(jobs: list[dict]):
    with get_connection() as conn:
        for job in jobs:
            conn.execute("""
                UPDATE jobs SET score = ?, mots_cles_matches = ?, raison = ?
                WHERE id = ?
            """, (
                job.get("score"),
                job.get("mots_cles_matches", ""),
                job.get("raison", ""),
                job["id"]
            ))
        conn.commit()
    print(f"✅ Scores sauvegardés pour {len(jobs)} offres")

def get_stats() -> dict:
    with get_connection() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active  = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'active'").fetchone()[0]
        removed = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'removed'").fetchone()[0]
        scored  = conn.execute("SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL").fetchone()[0]
    return {"total": total, "active": active, "removed": removed, "scored": scored}