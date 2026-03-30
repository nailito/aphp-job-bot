"""
pipeline_hcl.py
Orchestrateur du bot de veille HCL.

Étapes :
  1. Scraping     — scraper_hcl.run_scraper()
  2. Upsert BDD   — database_hcl.upsert_jobs()
  3. Filtre       — filter_hcl.run_filter()
  [Scoring — à ajouter plus tard]

Usage :
  python pipeline_hcl.py
"""

import os
import time
from datetime import datetime

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def notify(msg: str):
    print(msg)
    try:
        from notifier import send_telegram
        send_telegram(msg)
    except Exception as e:
        print(f"(Telegram failed: {e})")


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline():
    notify(f"🏥 Pipeline HCL lancé — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)
    print(f"🏥 Pipeline HCL — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    start = time.time()

    # Stats globales pour log_pipeline_run
    run_stats = {
        "total_scraped":    0,
        "new":              0,
        "removed":          0,
        "reactivated":      0,
        "ai_filtered":      0,
        "ai_passed":        0,
        "ai_rejected":      0,
        "scored":           0,
    }

    from database_hcl import get_connection, get_all_known_ids, upsert_jobs, log_pipeline_run

    conn = get_connection(DATABASE_URL)

    try:
        # ─────────────────────────
        # 1. SCRAPING
        # ─────────────────────────
        print("\n📡 Étape 1 — Scraping HCL...")
        notify("📡 Étape 1 — Scraping HCL en cours...")

        from scraper_hcl import run_scraper

        t0 = time.time()
        known_ids = get_all_known_ids(conn)
        scraped   = run_scraper(known_ids)
        elapsed   = int(time.time() - t0)

        run_stats["total_scraped"] = len(scraped)
        print(f"   ⏱ Scraping terminé en {elapsed}s — {len(scraped)} offres récupérées")
        notify(f"   📊 {len(scraped)} offres scrapées en {elapsed}s")

        # ─────────────────────────
        # 2. UPSERT BASE
        # ─────────────────────────
        print("\n💾 Étape 2 — Mise à jour base de données...")

        upsert_stats = upsert_jobs(conn, scraped)

        run_stats["new"]         = upsert_stats["new"]
        run_stats["removed"]     = upsert_stats["removed"]
        run_stats["reactivated"] = upsert_stats["reactivated"]

        print(
            f"   📊 {upsert_stats['new']} nouvelles | "
            f"{upsert_stats['reactivated']} réactivées | "
            f"{upsert_stats['removed']} retirées | "
            f"{upsert_stats['updated']} mises à jour"
        )
        notify(
            f"   📊 {upsert_stats['new']} nouvelles | "
            f"{upsert_stats['reactivated']} réactivées | "
            f"{upsert_stats['removed']} retirées"
        )

        if upsert_stats["new"] == 0 and upsert_stats["reactivated"] == 0:
            print("\n✅ Aucune nouvelle offre HCL — pipeline terminé.")
            notify("😴 HCL : aucune nouvelle offre aujourd'hui.")
            log_pipeline_run(conn, run_stats, source="hcl")
            return

        # ─────────────────────────
        # 3. FILTRE
        # ─────────────────────────
        print("\n🔍 Étape 3 — Filtrage...")
        notify("🔍 Étape 3 — Filtrage en cours...")

        from filter_hcl import run_filter

        t0           = time.time()
        filter_stats = run_filter(conn)
        elapsed      = int(time.time() - t0)

        kept     = filter_stats["auto_passed"] + filter_stats["fallback_passed"]
        rejected = filter_stats["rejected"]

        run_stats["ai_filtered"] = filter_stats["total"]
        run_stats["ai_passed"]   = kept
        run_stats["ai_rejected"] = rejected

        print(f"   ⏱ Filtrage terminé en {elapsed}s")
        notify(
            f"   📊 {filter_stats['total']} analysées → "
            f"{kept} retenues | {rejected} rejetées"
        )

        # ─────────────────────────
        # [SCORING — à brancher]
        # ─────────────────────────
        # from scorer_hcl import run_scorer
        # run_scorer(conn)

        # ─────────────────────────
        # 4. RÉSUMÉ
        # ─────────────────────────
        duration = int(time.time() - start)
        log_pipeline_run(conn, run_stats, source="hcl")

        summary = (
            f"\n✅ Pipeline HCL terminé en {duration}s\n"
            f"   🆕 {run_stats['new']} nouvelles\n"
            f"   ✅ {run_stats['ai_passed']} retenues filtre\n"
            f"   ❌ {run_stats['ai_rejected']} rejetées filtre"
        )
        print(summary)
        notify(summary)

    except Exception as e:
        duration = int(time.time() - start)
        log_pipeline_run(conn, run_stats, source="hcl")
        msg = f"❌ Erreur pipeline HCL : {e}"
        print(msg)
        notify(msg)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()