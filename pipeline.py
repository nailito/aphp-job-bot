import time
import sqlite3
from datetime import datetime

DB_PATH = "aphp_jobs.db"

def save_run(n_scraped, n_new, n_removed, n_passed_ai, n_rejected_ai, n_scored, status, duration):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO pipeline_runs
        (run_date, n_scraped, n_new, n_removed, n_passed_ai, n_rejected_ai, n_scored, status, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), n_scraped, n_new, n_removed,
          n_passed_ai, n_rejected_ai, n_scored, status, duration))
    conn.commit()
    conn.close()

def get_counts():
    conn = sqlite3.connect(DB_PATH)
    passed_ai  = conn.execute("SELECT COUNT(*) FROM jobs WHERE rejection_category = 'passed_filter_1' AND status = 'active'").fetchone()[0]
    rej_ai     = conn.execute("SELECT COUNT(*) FROM jobs WHERE rejection_category IN ('diplome_paramedical','surqualification','profil_inadequat') AND status = 'active'").fetchone()[0]
    scored     = conn.execute("SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL AND status = 'active'").fetchone()[0]
    conn.close()
    return passed_ai, rej_ai, scored

def run_pipeline():
    print("=" * 60)
    print(f"  🏥  Pipeline APHP — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    start = time.time()
    n_scraped = n_new = n_removed = 0

    try:
        # ── Étape 1 : Scraping ──────────────────────────────────────
        print("\n📡 Étape 1 — Scraping...")
        from scraper  import scrape_jobs
        from database import init_db, upsert_jobs
        from config   import APHP_JOBS_URL

        init_db()
        jobs = scrape_jobs(APHP_JOBS_URL, max_pages=115)
        diff = upsert_jobs(jobs)
        n_scraped  = len(jobs)
        n_new      = len(diff["new"])
        n_removed  = len(diff["removed"])
        print(f"   ✅ {n_scraped} offres scrappées — {n_new} nouvelles — {n_removed} retirées")

        if n_new == 0:
            print("\n✅ Aucune nouvelle offre — pipeline terminé.")
            save_run(n_scraped, 0, n_removed, 0, 0, 0, "no_new_offers", int(time.time() - start))
            return

        # ── Étape 2 : Filtre métier/contrat ─────────────────────────
        print("\n🚫 Étape 2 — Filtre métier/contrat...")
        from main import load_active_jobs, mark_rejected, reset_rejections
        from config import EXCLUDED_METIERS
        import sqlite3 as _sq

        EXCLUDED_CONTRATS = ["Stage", "CAE"]
        EXCLUDED_FILIERES = ["Rééducation", "Paramédical encadrement"]

        # Appliquer uniquement sur les nouvelles offres
        new_ids = {j["id"] for j in diff["new"]}
        conn = _sq.connect(DB_PATH)
        new_jobs = conn.execute("""
            SELECT id, title, metier, filiere, hopital, location,
                   contrat, teletravail, horaire, temps_travail,
                   date_publication, description, url
            FROM jobs WHERE id IN ({})
        """.format(",".join("?" * len(new_ids))), list(new_ids)).fetchall()
        conn.close()

        cols = ["id","title","metier","filiere","hopital","location",
                "contrat","teletravail","horaire","temps_travail",
                "date_publication","description","url"]
        new_jobs = [dict(zip(cols, r)) for r in new_jobs]

        n_rej_metier = 0
        for job in new_jobs:
            if job.get("metier","") in EXCLUDED_METIERS:
                mark_rejected(job["id"], "metier_exclu", f"Métier exclu : {job.get('metier','')}")
                n_rej_metier += 1
            elif job.get("contrat","") in EXCLUDED_CONTRATS:
                mark_rejected(job["id"], "metier_exclu", f"Contrat exclu : {job.get('contrat','')}")
                n_rej_metier += 1
            elif job.get("filiere","") in EXCLUDED_FILIERES:
                mark_rejected(job["id"], "metier_exclu", f"Filière exclue : {job.get('filiere','')}")
                n_rej_metier += 1

        print(f"   ✅ {n_rej_metier} rejetées — {len(new_jobs) - n_rej_metier} restantes")

        # ── Étape 3 : Filtre IA ─────────────────────────────────────
        print("\n🤖 Étape 3 — Filtre IA...")
        from filter_ai import run_filter_1
        run_filter_1()

        # ── Étape 4 : Scoring ───────────────────────────────────────
        print("\n🎯 Étape 4 — Scoring profil...")
        from scorer import run_scorer
        run_scorer()

        passed_ai, rej_ai, scored = get_counts()
        duration = int(time.time() - start)

        save_run(n_scraped, n_new, n_removed, passed_ai, rej_ai, scored, "success", duration)

        print(f"\n{'=' * 60}")
        print(f"  ✅  Pipeline terminé en {duration}s")
        print(f"  📊  {n_new} nouvelles | {passed_ai} passées IA | {scored} scorées")
        print(f"{'=' * 60}")

    except Exception as e:
        duration = int(time.time() - start)
        save_run(n_scraped, n_new, n_removed, 0, 0, 0, f"error: {e}", duration)
        print(f"\n❌ Erreur pipeline : {e}")
        raise

if __name__ == "__main__":
    run_pipeline()