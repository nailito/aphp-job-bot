from database import get_stats
from config   import EXCLUDED_METIERS
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL", "")
EXCLUDED_CONTRATS = ["Stage", "CAE"]
EXCLUDED_FILIERES = ["Rééducation", "Paramédical encadrement"]

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def load_active_jobs() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, metier, filiere, hopital, location,
                       contrat, teletravail, horaire, temps_travail,
                       date_publication, description, url
                FROM jobs WHERE status = 'active'
            """)
            rows = cur.fetchall()
    cols = ["id","title","metier","filiere","hopital","location",
            "contrat","teletravail","horaire","temps_travail",
            "date_publication","description","url"]
    return [dict(zip(cols, r)) for r in rows]

def mark_rejected(job_id: str, category: str, reason: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs SET rejection_category = %s, rejection_reason = %s
                WHERE id = %s
            """, (category, reason, job_id))
        conn.commit()

def reset_rejections():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs
                SET rejection_category = NULL, rejection_reason = NULL
                WHERE status = 'active'
                AND rejection_category = 'metier_exclu'
            """)
        conn.commit()

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Pipeline")
    print("=" * 55)

    jobs = load_active_jobs()
    print(f"\n📦 {len(jobs)} offres actives en base")

    reset_rejections()

    kept, rejected = [], []

    for job in jobs:
        if job.get("metier", "") in EXCLUDED_METIERS:
            mark_rejected(job["id"], "metier_exclu", f"Métier exclu : {job.get('metier','')}")
            rejected.append(job)
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