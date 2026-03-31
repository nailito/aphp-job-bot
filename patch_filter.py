"""
patch_deterministic.py

Applique rétroactivement tous les filtres déterministes (hors IA) sur les
offres déjà marquées 'pass', sans reconsommer de crédits Groq.

Ordre des filtres appliqués (identique à run_filter) :
    1. Contrat (stage, alternance)
    2. Titre
    3. Paramédical (diplômes stricts)
    4. Niveau de diplôme trop bas
    5. Filière

Les offres qui survivent à tous ces filtres restent 'pass' — elles ne sont
pas repassées à l'IA.
"""

import logging
import os
from tqdm import tqdm
from psycopg.rows import dict_row

from database_hcl import get_connection, update_ai_filter
from filter_hcl import (
    _reject_contrat,
    _reject_title,
    _reject_paramedical,
    _reject_diploma_level,
    _reject_filiere,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pipeline déterministe dans l'ordre de run_filter
DETERMINISTIC_FILTERS = [
    ("Contrat",         _reject_contrat),
    ("Titre",           _reject_title),
    ("Paramédical",     _reject_paramedical),
    ("Niveau diplôme",  _reject_diploma_level),
    ("Filière",         _reject_filiere),
]


def get_passed_offers(conn) -> list[dict]:
    """Récupère les offres actives déjà marquées 'pass'."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, titre, filiere, description, contrats
            FROM hcl_jobs
            WHERE status = 'active'
              AND ai_filter_decision = 'pass'
            ORDER BY first_seen_at DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def _normalize(job: dict) -> dict:
    """
    Adapte les noms de colonnes de la BDD aux noms attendus par filter_hcl.
    - 'contrats' (BDD) → 'contrat' (filter_hcl)
    """
    return {**job, "contrat": job.get("contrats", "")}


def run_patch(conn) -> dict:
    jobs = get_passed_offers(conn)
    total = len(jobs)
    stats = {
        "total": total,
        "inchangées": 0,
        **{label: 0 for label, _ in DETERMINISTIC_FILTERS},
    }

    logger.info(f"🔍 {total} offres 'pass' à vérifier...")

    for job in tqdm(jobs, desc="Patch déterministe"):
        job_id = job["id"]
        titre = job.get("titre", "")[:60]
        job_normalized = _normalize(job)

        rejected = False
        for label, filter_fn in DETERMINISTIC_FILTERS:
            result = filter_fn(job_normalized)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats[label] += 1
                logger.info(f"  ❌ {label} [{job_id}] {titre} — {reason}")
                rejected = True
                break

        if not rejected:
            stats["inchangées"] += 1

    total_rejected = sum(stats[label] for label, _ in DETERMINISTIC_FILTERS)
    print(f"\n📊 Résumé patch déterministe :")
    print(f"   Offres 'pass' analysées : {total}")
    for label, _ in DETERMINISTIC_FILTERS:
        if stats[label]:
            print(f"   ❌ Rejetées ({label:<16}) : {stats[label]}")
    print(f"   ❌ Total rejetées        : {total_rejected}")
    print(f"   ✅ Inchangées            : {stats['inchangées']}")
    return stats


if __name__ == "__main__":
    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = get_connection(DATABASE_URL)
    try:
        run_patch(conn)
    finally:
        conn.close()