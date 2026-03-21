from database import get_connection, get_stats, save_scores
from matcher  import score_jobs
from config   import EXCLUDED_METIERS
import sqlite3
import pandas as pd

DB_PATH = "aphp_jobs.db"

def load_active_jobs() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, horaire, temps_travail,
               date_publication, description, url
        FROM jobs WHERE status = 'active'
    """).fetchall()
    conn.close()
    cols = ["id","title","metier","filiere","hopital","location",
            "contrat","teletravail","horaire","temps_travail",
            "date_publication","description","url"]
    return [dict(zip(cols, r)) for r in rows]

def mark_rejected(job_id: str, category: str, reason: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs
        SET rejection_category = ?, rejection_reason = ?
        WHERE id = ?
    """, (category, reason, job_id))
    conn.commit()
    conn.close()

def reset_rejections():
    """Remet à zéro les rejets avant chaque run."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs
        SET rejection_category = NULL, rejection_reason = NULL
        WHERE status = 'active'
    """)
    conn.commit()
    conn.close()

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Pipeline")
    print("=" * 55)

    # Charger toutes les offres actives depuis la DB
    jobs = load_active_jobs()
    print(f"\n📦 {len(jobs)} offres actives en base")

    # Reset des rejets précédents
    reset_rejections()

    # ── Étape 1 : Filtre métier ──────────────────────────────
    kept, rejected_metier = [], []
    for job in jobs:
        if job.get("metier", "") in EXCLUDED_METIERS:
            rejected_metier.append(job)
            mark_rejected(
                job["id"],
                "metier_exclu",
                f"Métier exclu : {job.get('metier', 'inconnu')}"
            )
        else:
            kept.append(job)

    print(f"  🚫 Étape 1 — Filtre métier : {len(rejected_metier)} rejetées, {len(kept)} restantes")

    # ── Étape 2 : Scoring IA (quand tu seras prêt) ───────────
    # scored = score_jobs(kept)
    # save_scores(scored)
    # Pour l'instant on saute le scoring

    stats = get_stats()
    print(f"\n📊 Stats DB : {stats}")

if __name__ == "__main__":
    main()