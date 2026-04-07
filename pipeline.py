import time
import os
import psycopg as psycopg2
from datetime import datetime, timezone
from notifier import send_telegram

DATABASE_URL = os.getenv("DATABASE_URL", "")

def notify(msg):
    print(msg)
    try:
        send_telegram(msg)
    except Exception as e:
        print(f"(Telegram failed: {e})")

def get_connection():
    """Connexion fraîche avec keepalive TCP pour éviter les coupures SSL."""
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        # Keepalive TCP : ping toutes les 30s si idle
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        # Timeout de connexion
        connect_timeout=30,
    )
    return conn

def execute_with_retry(fn, retries=3, delay=5):
    """Exécute fn(conn) avec retry sur erreur de connexion."""
    for attempt in range(retries):
        try:
            with get_connection() as conn:
                return fn(conn)
        except psycopg2.OperationalError as e:
            if attempt < retries - 1:
                print(f"   ⚠️ DB error (tentative {attempt+1}/{retries}): {e}")
                time.sleep(delay)
            else:
                raise

def save_run(n_scraped, n_new, n_removed, n_passed_ai, n_rejected_ai, n_scored, status, duration):
    def _fn(conn):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pipeline_runs
                (run_at, source, total_scraped, new_offers, removed_offers,
                 ai_passed, ai_rejected, scored, status, duration_sec)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(timezone.utc), "aphp",
                n_scraped, n_new, n_removed,
                n_passed_ai, n_rejected_ai, n_scored,
                status, duration
            ))
        conn.commit()
    execute_with_retry(_fn)

def get_counts(new_ids: set):
    if not new_ids:
        return 0, 0, 0
    placeholders = ",".join(["%s"] * len(new_ids))

    def _fn(conn):
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM jobs WHERE id IN ({placeholders}) AND rejection_category = 'passed_filter_1'", list(new_ids))
            passed_ai = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM jobs WHERE id IN ({placeholders}) AND rejection_category IN ('diplome_paramedical','surqualification','profil_inadequat')", list(new_ids))
            rej_ai = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM jobs WHERE id IN ({placeholders}) AND score IS NOT NULL", list(new_ids))
            scored = cur.fetchone()[0]
        return passed_ai, rej_ai, scored

    return execute_with_retry(_fn)

def fetch_new_jobs(new_ids: set):
    """Récupère les jobs depuis la DB — connexion fraîche, indépendante du scraping."""
    placeholders = ",".join(["%s"] * len(new_ids))
    cols = ["id","title","metier","filiere","hopital","location",
            "contrat","teletravail","horaire","temps_travail",
            "date_publication","description","url"]

    def _fn(conn):
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, title, metier, filiere, hopital, location,
                       contrat, teletravail, horaire, temps_travail,
                       date_publication, description, url
                FROM jobs WHERE id IN ({placeholders})
            """, list(new_ids))
            rows = cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]

    return execute_with_retry(_fn)

def run_pipeline():
    notify(f"🚀 Pipeline lancé — {datetime.now().strftime('%H:%M')}")
    print("=" * 60)
    print(f"🏥 Pipeline APHP — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    start = time.time()
    n_scraped = n_new = n_removed = 0

    try:
        # ─────────────────────────
        # 1. SCRAPING
        # ─────────────────────────
        print("\n📡 Étape 1 — Scraping...")
        notify("📡 Étape 1 — Scraping en cours...")
        from scraper  import scrape_jobs
        from database import init_db, upsert_jobs
        from config   import APHP_JOBS_URL

        init_db()

        t0 = time.time()
        jobs = scrape_jobs(APHP_JOBS_URL, max_pages=115)
        print(f"   ⏱ Scraping terminé en {int(time.time()-t0)}s")

        # upsert_jobs ouvre sa propre connexion — pas de souci ici
        diff = upsert_jobs(jobs)

        n_scraped = len(jobs)
        n_new     = len(diff["new"])
        n_removed = len(diff["removed"])

        print(f"   📊 {n_scraped} scrapées | {n_new} nouvelles | {n_removed} retirées")
        notify(f"   📊 {n_scraped} scrapées | {n_new} nouvelles | {n_removed} retirées")

        if n_new == 0:
            print("\n✅ Aucune nouvelle offre — pipeline terminé.")
            notify("😴 Aucune nouvelle offre aujourd'hui")
            save_run(n_scraped, 0, n_removed, 0, 0, 0, "no_new_offers", int(time.time() - start))
            return

        # ─────────────────────────
        # 2. FILTRE MÉTIER
        # ─────────────────────────
        print("\n🚫 Étape 2 — Filtre métier/contrat...")
        notify("\n🚫 Étape 2 — Filtre métier/contrat...")
        from main   import mark_rejected
        from config import EXCLUDED_METIERS

        EXCLUDED_CONTRATS = ["Stage", "CAE"]
        EXCLUDED_FILIERES = ["Rééducation", "Paramédical encadrement"]

        new_ids = {j["id"] for j in diff["new"]}

        # ✅ Connexion fraîche, indépendante du scraping
        new_jobs = fetch_new_jobs(new_ids)

        n_rej_metier = 0

        for i, job in enumerate(new_jobs, 1):
            print(f"   [{i}/{len(new_jobs)}] {job['title'][:60]}")

            if job.get("metier","") in EXCLUDED_METIERS:
                mark_rejected(job["id"], "metier_exclu", f"Métier exclu : {job.get('metier','')}")
                n_rej_metier += 1
            elif job.get("contrat","") in EXCLUDED_CONTRATS:
                mark_rejected(job["id"], "metier_exclu", f"Contrat exclu : {job.get('contrat','')}")
                n_rej_metier += 1
            elif job.get("filiere","") in EXCLUDED_FILIERES:
                mark_rejected(job["id"], "metier_exclu", f"Filière exclue : {job.get('filiere','')}")
                n_rej_metier += 1

        print(f"   📊 {n_rej_metier} rejetées | {len(new_jobs)-n_rej_metier} restantes")
        notify(f"   📊 {n_rej_metier} rejetées | {len(new_jobs)-n_rej_metier} restantes")

        # ─────────────────────────
        # 3. FILTRE IA
        # ─────────────────────────
        print("\n🤖 Étape 3 — Filtre IA...")
        notify("\n🤖 Étape 3 — Filtre IA...")
        from filter_ai import run_filter_1

        t0 = time.time()
        run_filter_1()
        print(f"   ⏱ Filtre IA terminé en {int(time.time()-t0)}s")
        notify(f"   ⏱ Filtre IA terminé en {int(time.time()-t0)}s")

        # ─────────────────────────
        # 4. SCORING
        # ─────────────────────────
        print("\n🎯 Étape 4 — Scoring profil...")
        notify("\n🎯 Étape 4 — Scoring profil...")
        from scorer import run_scorer

        t0 = time.time()
        run_scorer()
        print(f"   ⏱ Scoring terminé en {int(time.time()-t0)}s")
        notify(f"   ⏱ Scoring terminé en {int(time.time()-t0)}s")

        # ─────────────────────────
        # 5. STATS
        # ─────────────────────────
        passed_ai, rej_ai, scored = get_counts(new_ids)
        duration = int(time.time() - start)

        print("\n📊 Résumé final :")
        print(f"   🆕 {n_new} nouvelles")
        print(f"   ✅ {passed_ai} passées IA")
        print(f"   ❌ {rej_ai} rejetées IA")
        print(f"   🎯 {scored} scorées")

        notify(f"📊 Résumé final :\n   🆕 {n_new} nouvelles\n   ✅ {passed_ai} passées IA\n   ❌ {rej_ai} rejetées IA\n   🎯 {scored} scorées")

        save_run(n_scraped, n_new, n_removed, passed_ai, rej_ai, scored, "success", duration)

        print(f"\n{'=' * 60}")
        print(f"✅ Pipeline terminé en {duration}s")
        print(f"{'=' * 60}")
        notify(f"\n✅ Pipeline terminé en {duration}s")

    except Exception as e:
        duration = int(time.time() - start)
        save_run(n_scraped, n_new, n_removed, 0, 0, 0, f"error: {e}", duration)
        print(f"\n❌ Erreur pipeline : {e}")
        send_telegram(f"❌ Erreur pipeline : {str(e)}")
        raise

if __name__ == "__main__":
    run_pipeline()