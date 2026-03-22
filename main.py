as from database import get_connection, get_stats
from config   import EXCLUDED_METIERS, EXCLUDED_FILIERES
import sqlite3

DB_PATH = "aphp_jobs.db"

EXCLUDED_CONTRATS = ["Stage", "CAE"]

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
        UPDATE jobs SET rejection_category = ?, rejection_reason = ?
        WHERE id = ?
    """, (category, reason, job_id))
    conn.commit()
    conn.close()

def reset_rejections():
    """Remet à zéro uniquement les rejets métier/contrat, pas les résultats IA."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs
        SET rejection_category = NULL, rejection_reason = NULL
        WHERE status = 'active'
        AND rejection_category = 'metier_exclu'
    """)
    conn.commit()
    conn.close()

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Pipeline")
    print("=" * 55)

    jobs = load_active_jobs()
    print(f"\n📦 {len(jobs)} offres actives en base")

    reset_rejections()

    # Debug
    stages = [j for j in jobs if j.get("contrat", "") in EXCLUDED_CONTRATS]
    #print(f"  🔍 Debug : {len(stages)} offres Stage/CAE trouvées")
    #for j in stages[:3]:
    #    print(f"     contrat='{j.get('contrat')}' | repr={repr(j.get('contrat'))}")

    kept, rejected = [], []

    for job in jobs:
        # Filtre métier
        if job.get("metier", "") in EXCLUDED_METIERS:
            mark_rejected(job["id"], "metier_exclu", f"Métier exclu : {job.get('metier','')}")
            rejected.append(job)

        # Filtre contrat
        elif job.get("contrat", "") in EXCLUDED_CONTRATS:
            mark_rejected(job["id"], "metier_exclu", f"Contrat exclu : {job.get('contrat','')}")
            rejected.append(job)

        elif job.get("filiere", "") in EXCLUDED_FILIERES:
            mark_rejected(job["id"], "metier_exclu", f"Filière exclue : {job.get('filiere','')}")
            rejected.append(job)    

        else:
            kept.append(job)

    print(f"  🚫 Étape 1 — {len(rejected)} rejetées, {len(kept)} restantes")

    stats = get_stats()
    print(f"\n📊 Stats DB : {stats}")

if __name__ == "__main__":
    main()