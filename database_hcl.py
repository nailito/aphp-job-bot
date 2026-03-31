"""
database_hcl.py
Couche d'accès Supabase pour les offres HCL (table hcl_jobs).
Miroir de database.py, adapté à la structure JetEngine/HCL.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg as psycopg2
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def get_connection(database_url: str):
    return psycopg2.connect(database_url)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def get_all_known_ids(conn) -> set[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM hcl_jobs")
        return {row[0] for row in cur.fetchall()}


def get_active_offers(conn) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM hcl_jobs WHERE status = 'active' ORDER BY first_seen_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def get_offers_to_score(conn) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT * FROM hcl_jobs
            WHERE status = 'active'
              AND ai_filter_decision = 'pass'
              AND score IS NULL
            ORDER BY first_seen_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def get_offers_to_filter(conn) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT * FROM hcl_jobs
            WHERE status = 'active'
              AND ai_filter_decision IS NULL
            ORDER BY first_seen_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Écriture — upsert principal
# ---------------------------------------------------------------------------

def upsert_jobs(conn, scraped_offers: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    scraped_ids = {o["id"] for o in scraped_offers}

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, status, miss_count FROM hcl_jobs")
        known = {row["id"]: dict(row) for row in cur.fetchall()}

    stats = {"new": 0, "reactivated": 0, "removed": 0, "updated": 0}

    with conn.cursor() as cur:
        for offer in scraped_offers:
            oid = offer["id"]

            if oid not in known:
                cur.execute("""
                    INSERT INTO hcl_jobs (
                        id, titre, url, localisation, contrats,
                        filiere, duree, date_debut, description,
                        status, miss_count,
                        first_seen_at, last_seen_at
                    ) VALUES (
                        %(id)s, %(titre)s, %(url)s, %(localisation)s, %(contrats)s,
                        %(filiere)s, %(duree)s, %(date_debut)s, %(description)s,
                        'active', 0,
                        %(now)s, %(now)s
                    )
                """, {**offer, "now": now})
                stats["new"] += 1

            else:
                existing = known[oid]
                was_removed = existing["status"] == "removed"

                if offer.get("description") is not None:
                    cur.execute("""
                        UPDATE hcl_jobs SET
                            titre = %(titre)s,
                            url = %(url)s,
                            localisation = %(localisation)s,
                            contrats = %(contrats)s,
                            filiere = %(filiere)s,
                            duree = %(duree)s,
                            date_debut = %(date_debut)s,
                            description = %(description)s,
                            status = 'active',
                            miss_count = 0,
                            last_seen_at = %(now)s
                        WHERE id = %(id)s
                    """, {**offer, "now": now})
                else:
                    cur.execute("""
                        UPDATE hcl_jobs SET
                            titre = %(titre)s,
                            url = %(url)s,
                            localisation = %(localisation)s,
                            contrats = %(contrats)s,
                            filiere = %(filiere)s,
                            duree = %(duree)s,
                            date_debut = %(date_debut)s,
                            status = 'active',
                            miss_count = 0,
                            last_seen_at = %(now)s
                        WHERE id = %(id)s
                    """, {**offer, "now": now})

                if was_removed:
                    stats["reactivated"] += 1
                else:
                    stats["updated"] += 1

        missing_ids = set(known.keys()) - scraped_ids
        for oid in missing_ids:
            if known[oid]["status"] == "removed":
                continue

            new_miss = known[oid]["miss_count"] + 1
            if new_miss >= 5:
                cur.execute("""
                    UPDATE hcl_jobs
                    SET miss_count = %s, status = 'removed'
                    WHERE id = %s
                """, (new_miss, oid))
                stats["removed"] += 1
                logger.info(f"Offre HCL {oid} retirée (miss_count={new_miss})")
            else:
                cur.execute("""
                    UPDATE hcl_jobs
                    SET miss_count = %s
                    WHERE id = %s
                """, (new_miss, oid))

    conn.commit()
    logger.info(
        f"upsert_jobs HCL : +{stats['new']} nouvelles, "
        f"+{stats['reactivated']} réactivées, "
        f"-{stats['removed']} retirées, "
        f"~{stats['updated']} mises à jour"
    )
    return stats


# ---------------------------------------------------------------------------
# Écriture — pipeline IA
# ---------------------------------------------------------------------------

def update_ai_filter(conn, job_id: int, decision: str, reason: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE hcl_jobs
            SET ai_filter_decision = %s, ai_filter_reason = %s
            WHERE id = %s
        """, (decision, reason, job_id))
    conn.commit()


def update_score(conn, job_id: int, score: int, analysis: str):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE hcl_jobs
            SET score = %s, score_analysis = %s, scored_at = %s
            WHERE id = %s
        """, (score, analysis, now, job_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------

def log_pipeline_run(conn, stats: dict, source: str = "hcl"):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_runs (
                run_at, source,
                total_scraped, new_offers, removed_offers, reactivated_offers,
                ai_filtered, ai_passed, ai_rejected,
                scored
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            now, source,
            stats.get("total_scraped", 0),
            stats.get("new", 0),
            stats.get("removed", 0),
            stats.get("reactivated", 0),
            stats.get("ai_filtered", 0),
            stats.get("ai_passed", 0),
            stats.get("ai_rejected", 0),
            stats.get("scored", 0),
        ))
    conn.commit()