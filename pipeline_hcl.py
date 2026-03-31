"""
pipeline_hcl.py
Pipeline robuste HCL — version refactorisée

Améliorations :
- Pas d'arrêt prématuré
- Gestion d'erreurs par étape
- Logs structurés
- Idempotence (filtre uniquement NULL)
- Stats fiables même en cas d'erreur partielle
"""

import os
import time
import logging
from datetime import datetime

import psycopg as psycopg2


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL manquant")


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def notify(msg: str):
    logger.info(msg)
    try:
        from notifier import send_telegram
        send_telegram(msg)
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def safe_step(step_name, func, *args, **kwargs):
    """
    Exécute une étape avec gestion d’erreur isolée.
    Ne casse pas tout le pipeline si une étape échoue.
    """
    logger.info(f"▶ {step_name} — START")
    t0 = time.time()

    try:
        result = func(*args, **kwargs)
        elapsed = int(time.time() - t0)

        logger.info(f"✔ {step_name} — OK ({elapsed}s)")
        return result, None

    except Exception as e:
        elapsed = int(time.time() - t0)

        logger.error(f"✖ {step_name} — FAIL ({elapsed}s) : {e}")
        notify(f"❌ {step_name} failed: {e}")

        return None, str(e)


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────

def run_pipeline():

    start = time.time()
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    notify(f"🏥 Pipeline HCL lancé — {now_str}")
    print("=" * 60)
    print(f"🏥 Pipeline HCL — {now_str}")
    print("=" * 60)

    from database_hcl import (
        get_connection,
        get_all_known_ids,
        upsert_jobs,
        log_pipeline_run
    )

    conn = get_connection(DATABASE_URL)

    # Stats globales
    run_stats = {
        "total_scraped": 0,
        "new": 0,
        "removed": 0,
        "reactivated": 0,
        "ai_filtered": 0,
        "ai_passed": 0,
        "ai_rejected": 0,
        "scored": 0,
        "errors": []
    }

    try:
        # ─────────────────────────
        # 1. SCRAPING
        # ─────────────────────────

        def step_scraping():
            from scraper_hcl import run_scraper

            known_ids = get_all_known_ids(conn)
            scraped = run_scraper(known_ids)

            return scraped

        scraped, err = safe_step("SCRAPING", step_scraping)

        if err:
            run_stats["errors"].append(("scraping", err))
            scraped = []

        run_stats["total_scraped"] = len(scraped or [])
        notify(f"📊 {len(scraped or [])} offres scrapées")

        # ─────────────────────────
        # 2. UPSERT DB
        # ─────────────────────────

        def step_upsert():
            return upsert_jobs(conn, scraped)

        upsert_stats, err = safe_step("UPSERT", step_upsert)

        if err:
            run_stats["errors"].append(("upsert", err))
            upsert_stats = {
                "new": 0,
                "removed": 0,
                "reactivated": 0,
                "updated": 0
            }

        run_stats["new"] = upsert_stats["new"]
        run_stats["removed"] = upsert_stats["removed"]
        run_stats["reactivated"] = upsert_stats["reactivated"]

        notify(
            f"📊 {upsert_stats['new']} new | "
            f"{upsert_stats['reactivated']} reactivated | "
            f"{upsert_stats['removed']} removed"
        )

        # ─────────────────────────
        # 3. FILTRE (TOUJOURS exécuté)
        # ─────────────────────────

        def step_filter():
            from filter_hcl import run_filter
            return run_filter(conn)

        filter_stats, err = safe_step("FILTER", step_filter)

        if err:
            run_stats["errors"].append(("filter", err))
            filter_stats = {
                "total": 0,
                "auto_passed": 0,
                "fallback_passed": 0,
                "rejected": 0
            }

        kept = filter_stats["auto_passed"] + filter_stats["fallback_passed"]
        rejected = filter_stats["rejected"]

        run_stats["ai_filtered"] = filter_stats["total"]
        run_stats["ai_passed"] = kept
        run_stats["ai_rejected"] = rejected

        notify(
            f"📊 {filter_stats['total']} analysées → "
            f"{kept} retenues | {rejected} rejetées"
        )

        # ─────────────────────────
        # 4. SCORING (optionnel)
        # ─────────────────────────

        def step_scoring():
            from scorer_hcl import run_scorer
            return run_scorer(conn)

        try:
            scoring_enabled = True  # toggle facile

            if scoring_enabled:
                scoring_stats, err = safe_step("SCORING", step_scoring)

                if err:
                    run_stats["errors"].append(("scoring", err))
                else:
                    run_stats["scored"] = scoring_stats.get("scored", 0)

        except ImportError:
            logger.info("SCORING module absent (skip)")

        # ─────────────────────────
        # 5. LOG FINAL
        # ─────────────────────────

        duration = int(time.time() - start)

        log_pipeline_run(conn, run_stats, source="hcl")

        summary = (
            f"\n✅ Pipeline HCL terminé en {duration}s\n"
            f"🆕 {run_stats['new']} nouvelles\n"
            f"🔍 {run_stats['ai_filtered']} filtrées\n"
            f"✅ {run_stats['ai_passed']} retenues\n"
            f"❌ {run_stats['ai_rejected']} rejetées"
        )

        if run_stats["errors"]:
            summary += f"\n⚠️ {len(run_stats['errors'])} erreurs partielles"

        print(summary)
        notify(summary)

    except Exception as e:
        duration = int(time.time() - start)
        logger.exception("Pipeline crash global")
        
        try:
            conn.rollback()  # ← remet la connexion dans un état sain
            log_pipeline_run(conn, run_stats, source="hcl")
        except Exception as log_err:
            logger.error(f"Impossible de logger le crash : {log_err}")
        
        msg = f"❌ Crash pipeline HCL ({duration}s): {e}"
        notify(msg)
        raise

    finally:
        conn.close()

# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    run_pipeline()