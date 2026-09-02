# database_aphp

import os
import psycopg as psycopg2
from datetime import datetime

from database_schema import initialize_schema

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_connection(url: str | None = None):
    database_url = url or DATABASE_URL
    if not database_url:
        raise ValueError("DATABASE_URL manquant")
    return psycopg2.connect(database_url)


def init_db():
    with get_connection() as conn:
        initialize_schema(conn)
    print("✅ Schéma PostgreSQL initialisé")


def get_all_known_ids() -> set[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM jobs")
            return {row[0] for row in cur.fetchall()}


# ─────────────────────────────────────────────
# FONCTIONS FILTRE
# ─────────────────────────────────────────────


def get_offers_to_filter(conn) -> list[dict]:
    """Retourne les offres actives non encore filtrées (ou marquées à_trier)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, metier, filiere, contrat, date_publication, description
            FROM jobs
            WHERE status = 'active'
            AND (rejection_category IS NULL OR rejection_category = 'a_trier')
        """)
        rows = cur.fetchall()
    cols = ["id", "title", "metier", "filiere", "contrat", "date_publication", "description"]
    return [dict(zip(cols, r)) for r in rows]


def update_ai_filter(
    conn,
    job_id: str,
    decision: str,
    reason: str,
    category: str | None = None,
):
    """
    Met à jour rejection_category et rejection_reason d'une offre.
    decision : "pass" → rejection_category = 'passed_filter_1'
    decision : "reject" → rejection_category = category (ou "rejected" par défaut)
    """
    stored_category = "passed_filter_1" if decision == "pass" else (category or "rejected")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET rejection_category = %s, rejection_reason = %s
            WHERE id = %s
        """,
            (stored_category, reason, job_id),
        )
    conn.commit()


# ─────────────────────────────────────────────
# UPSERT / SCRAPING
# ─────────────────────────────────────────────


def upsert_jobs(jobs: list[dict]) -> dict:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM jobs")
            rows = cur.fetchall()
            existing_ids = {r[0] for r in rows if r[1] == "active"}
            all_known_ids = {r[0] for r in rows}

            site_ids = {j["id"] for j in jobs}
            new_ids = site_ids - all_known_ids
            missing_ids = existing_ids - site_ids
            new_jobs = [j for j in jobs if j["id"] in new_ids]

            for job in new_jobs:
                cur.execute(
                    """
                    INSERT INTO jobs (
                        id, title, metier, filiere, hopital, location,
                        contrat, teletravail, horaire, temps_travail,
                        date_publication, description, url,
                        first_seen, last_seen, status
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active')
                    ON CONFLICT (id) DO NOTHING
                """,
                    (
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
                    ),
                )

            reactivated = (all_known_ids - existing_ids) & site_ids
            for job_id in reactivated:
                cur.execute(
                    """
                    UPDATE jobs SET status = 'active', miss_count = 0, last_seen = %s
                    WHERE id = %s
                """,
                    (now, job_id),
                )

            for job in jobs:
                if job["id"] in existing_ids:
                    cur.execute(
                        "UPDATE jobs SET last_seen = %s, miss_count = 0 WHERE id = %s",
                        (now, job["id"]),
                    )

            newly_removed = set()
            if missing_ids:
                placeholders = ",".join(["%s"] * len(missing_ids))
                cur.execute(
                    f"""
                    UPDATE jobs SET miss_count = COALESCE(miss_count, 0) + 1
                    WHERE id IN ({placeholders})
                """,
                    list(missing_ids),
                )

                cur.execute(
                    f"""
                    UPDATE jobs SET status = 'removed'
                    WHERE id IN ({placeholders}) AND miss_count >= 5
                    RETURNING id
                """,
                    list(missing_ids),
                )
                newly_removed = {r[0] for r in cur.fetchall()}

        conn.commit()

    print(f"  🆕 {len(new_jobs)} nouvelles offres")
    print(f"  🗑️  {len(newly_removed)} offres retirées (miss >= 5)")
    print(f"  ⚠️  {len(missing_ids)} absentes ce run (miss_count +1)")
    print(f"  🔄  {len(reactivated)} offres réactivées")
    print(f"  ♻️  {len(existing_ids & site_ids)} offres déjà connues")
    return {"new": new_jobs, "removed": list(newly_removed)}


# ─────────────────────────────────────────────
# SCORES / STATS / FEEDBACKS
# ─────────────────────────────────────────────


def save_scores(jobs: list[dict]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for job in jobs:
                cur.execute(
                    """
                    UPDATE jobs SET score=%s, mots_cles_matches=%s, raison=%s
                    WHERE id=%s
                """,
                    (
                        job.get("score"),
                        job.get("mots_cles_matches", ""),
                        job.get("raison", ""),
                        job["id"],
                    ),
                )
        conn.commit()
    print(f"✅ Scores sauvegardés pour {len(jobs)} offres")


def get_stats() -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'active'")  # bugfix
            active = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'removed'")
            removed = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL")
            scored = cur.fetchone()[0]
    return {"total": total, "active": active, "removed": removed, "scored": scored}


def save_feedback(job_id: str, decision: str, tags: list, commentaire: str):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM feedbacks WHERE job_id = %s", (job_id,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE feedbacks
                    SET decision=%s, tags=%s, commentaire=%s, created_at=%s
                    WHERE job_id=%s
                """,
                    (decision, str(tags), commentaire, now, job_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO feedbacks (job_id, decision, tags, commentaire, created_at)
                    VALUES (%s,%s,%s,%s,%s)
                """,
                    (job_id, decision, str(tags), commentaire, now),
                )

            cur.execute(
                """
                UPDATE jobs SET rejection_category = 'reviewed' WHERE id = %s
            """,
                (job_id,),
            )

        conn.commit()


def get_feedbacks() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT f.job_id, f.decision, f.tags, f.commentaire, f.created_at,
                       j.title, j.metier, j.hopital, j.location, j.url
                FROM feedbacks f
                JOIN jobs j ON f.job_id = j.id
                ORDER BY f.created_at DESC
            """)
            rows = cur.fetchall()
    cols = [
        "job_id",
        "decision",
        "tags",
        "commentaire",
        "created_at",
        "title",
        "metier",
        "hopital",
        "location",
        "url",
    ]
    return [dict(zip(cols, r)) for r in rows]


def delete_feedback(job_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM feedbacks WHERE job_id = %s", (job_id,))
        conn.commit()


def get_application(job_id: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM applications WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))


def save_application(job_id: str, **kwargs):
    """Upsert une application — passe les champs à mettre à jour en kwargs."""
    fields = {k: v for k, v in kwargs.items()}
    fields["updated_at"] = datetime.now().isoformat()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT job_id FROM applications WHERE job_id = %s", (job_id,))
            exists = cur.fetchone()

            if exists:
                set_clause = ", ".join([f"{k} = %s" for k in fields])
                cur.execute(
                    f"UPDATE applications SET {set_clause} WHERE job_id = %s",
                    list(fields.values()) + [job_id],
                )
            else:
                fields["job_id"] = job_id
                cols = ", ".join(fields.keys())
                vals = ", ".join(["%s"] * len(fields))
                cur.execute(
                    f"INSERT INTO applications ({cols}) VALUES ({vals})", list(fields.values())
                )
        conn.commit()
