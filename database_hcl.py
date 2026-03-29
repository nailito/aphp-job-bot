"""
database_hcl.py
Couche d'accès Supabase pour les offres HCL (table hcl_jobs).
Miroir de database.py, adapté à la structure JetEngine/HCL.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

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
    """
    Retourne tous les IDs présents en base (actifs ET retirés),
    indispensable pour le suivi des miss_count et la réactivation.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM hcl_jobs")
        return {row[0] for row in cur.fetchall()}


def get_active_offers(conn) -> list[dict]:
    """Retourne toutes les offres actives (non retirées)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM hcl_jobs WHERE status = 'active' ORDER BY first_seen_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def get_offers_to_score(conn) -> list[dict]:
    """Offres ayant passé le filtre IA mais pas encore scorées."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM hcl_jobs
            WHERE status = 'active'
              AND ai_filter_decision = 'pass'
              AND score IS NULL
            ORDER BY first_seen_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def get_offers_to_filter(conn) -> list[dict]:
    """Offres actives sans décision IA."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
    """
    Synchronise les offres scrapées avec la base.

    Logique :
    - Nouvelle offre → INSERT
    - Offre existante vue → UPDATE last_seen_at + reset miss_count + réactivation éventuelle
    - Offre connue mais absente du scraping → incrément miss_count
    - miss_count >= 5 → status = 'removed'

    Returns:
        dict avec les compteurs new, reactivated, removed, updated
    """
    now = datetime.now(timezone.utc)
    scraped_ids = {o["id"] for o in scraped_offers}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Récupère TOUS les jobs connus (actifs + retirés)
        cur.execute("SELECT id, status, miss_count FROM hcl_jobs")
        known = {row["id"]: dict(row) for row in cur.fetchall()}

    stats = {"new": 0, "reactivated": 0, "removed": 0, "updated": 0}

    with conn.cursor() as cur:
        # --- Offres vues dans le scraping
        for offer in scraped_offers:
            oid = offer["id"]

            if oid not in known:
                # Nouvelle offre
                cur.execute("""
                    INSERT INTO hcl_jobs (
                        id, titre, url, localisation, contrats,
                        duree, date_debut, description,
                        status, miss_count,
                        first_seen_at, last_seen_at
                    ) VALUES (
                        %(id)s, %(titre)s, %(url)s, %(localisation)s, %(contrats)s,
                        %(duree)s, %(date_debut)s, %(description)s,
                        'active', 0,
                        %(now)s, %(now)s
                    )
                """, {**offer, "now": now})
                stats["new"] += 1

            else:
                existing = known[oid]
                was_removed = existing["status"] == "removed"

                # Met à jour les champs de listing + réinitialise le miss_count
                # Ne touche PAS à description si elle est déjà renseignée
                # (offer["description"] est None pour les offres déjà connues)
                if offer.get("description") is not None:
                    cur.execute("""
                        UPDATE hcl_jobs SET
                            titre = %(titre)s,
                            url = %(url)s,
                            localisation = %(localisation)s,
                            contrats = %(contrats)s,
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

        # --- Offres absentes du scraping → incrément miss_count
        missing_ids = set(known.keys()) - scraped_ids
        for oid in missing_ids:
            if known[oid]["status"] == "removed":
                continue  # déjà retiré, pas besoin de toucher

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
    """Enregistre la décision du filtre IA (pass/reject)."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE hcl_jobs
            SET ai_filter_decision = %s, ai_filter_reason = %s
            WHERE id = %s
        """, (decision, reason, job_id))
    conn.commit()


def update_score(conn, job_id: int, score: int, analysis: str):
    """Enregistre le score et l'analyse."""
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
    """Enregistre un run dans la table pipeline_runs (partagée)."""
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