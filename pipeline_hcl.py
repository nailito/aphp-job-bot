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
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

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
        logger.warning(f"Telegram failed: {type(e).__name__}")


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

        error_type = type(e).__name__
        logger.error(f"✖ {step_name} — FAIL ({elapsed}s) : {error_type}")
        notify(f"❌ {step_name} failed: {error_type}")

        return None, error_type


# ─────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────


def run_pipeline():

    start = time.time()
    now_str = datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")

    notify(f"🏥 Pipeline HCL lancé — {now_str}")
    print("=" * 60)
    print(f"🏥 Pipeline HCL — {now_str}")
    print("=" * 60)

    from database_hcl import get_connection, get_all_known_ids, upsert_jobs, log_pipeline_run
    from database_schema import initialize_schema

    conn = None

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
        "errors": [],
    }

    try:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL manquant")
        conn = get_connection(DATABASE_URL)
        initialize_schema(conn)
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
            conn.rollback()

        run_stats["total_scraped"] = len(scraped or [])
        notify(f"📊 {len(scraped or [])} offres scrapées")

        # ─────────────────────────
        # 2. UPSERT DB
        # ─────────────────────────

        upsert_stats = {
            "new": 0,
            "removed": 0,
            "reactivated": 0,
            "updated": 0,
        }

        if scraped:

            def step_upsert():
                return upsert_jobs(conn, scraped)

            upsert_result, err = safe_step("UPSERT", step_upsert)
            if err:
                run_stats["errors"].append(("upsert", err))
                conn.rollback()
            elif upsert_result:
                upsert_stats = upsert_result
        else:
            logger.warning("UPSERT ignoré: aucun snapshot HCL complet disponible")

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
            conn.rollback()
            filter_stats = {"total": 0, "auto_passed": 0, "fallback_passed": 0, "rejected": 0}
        pending_filter = filter_stats.get("errors", 0) + max(
            filter_stats.get("ai_errors", 0), filter_stats.get("skipped", 0)
        )
        if pending_filter:
            run_stats["errors"].append(("filter", f"{pending_filter} offres non traitées"))

        kept = (
            filter_stats["auto_passed"]
            + filter_stats["fallback_passed"]
            + filter_stats.get("ai_passed", 0)
        )
        rejected = filter_stats["rejected"]

        run_stats["ai_filtered"] = filter_stats["total"]
        run_stats["ai_passed"] = kept
        run_stats["ai_rejected"] = rejected

        notify(f"📊 {filter_stats['total']} analysées → {kept} retenues | {rejected} rejetées")

        # ─────────────────────────
        # 4. SCORING
        # ─────────────────────────

        def step_scoring():
            from scorer_hcl import run_scorer

            return run_scorer(conn)

        scoring_stats, err = safe_step("SCORING", step_scoring)
        if err:
            run_stats["errors"].append(("scoring", err))
            conn.rollback()
        else:
            run_stats["scored"] = scoring_stats.get("scored", 0)
            pending_scoring = sum(scoring_stats.get(key, 0) for key in ("errors", "skipped"))
            if pending_scoring:
                run_stats["errors"].append(("scoring", f"{pending_scoring} offres non traitées"))

        # ─────────────────────────
        # 5. LOG FINAL
        # ─────────────────────────

        duration = int(time.time() - start)

        if run_stats["errors"]:
            details = "; ".join(f"{step}: {error}" for step, error in run_stats["errors"])
            raise RuntimeError(f"Pipeline HCL incomplet: {details}")

        run_stats["status"] = "success"
        run_stats["duration_sec"] = duration
        log_pipeline_run(conn, run_stats, source="hcl")

        summary = (
            f"\n✅ Pipeline HCL terminé en {duration}s\n"
            f"🆕 {run_stats['new']} nouvelles\n"
            f"🔍 {run_stats['ai_filtered']} filtrées\n"
            f"✅ {run_stats['ai_passed']} retenues\n"
            f"❌ {run_stats['ai_rejected']} rejetées"
        )

        print(summary)
        notify(summary)

    except Exception as e:
        duration = int(time.time() - start)
        error_type = type(e).__name__
        logger.error(f"Pipeline HCL en échec : {error_type}")
        run_stats["status"] = f"error: {error_type}"
        run_stats["duration_sec"] = duration

        try:
            if conn is not None:
                conn.rollback()
                log_pipeline_run(conn, run_stats, source="hcl")
        except Exception as log_err:
            logger.error(f"Impossible de logger le crash : {type(log_err).__name__}")

        msg = f"❌ Échec pipeline HCL ({duration}s): {error_type}"
        notify(msg)
        raise RuntimeError(f"Pipeline HCL en échec ({error_type})") from None

    finally:
        if conn is not None:
            conn.close()


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    run_pipeline()
