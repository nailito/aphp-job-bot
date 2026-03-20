# ============================================================
#  main.py  —  Orchestrateur du bot APHP
# ============================================================
import sys
from scraper  import scrape_jobs
from matcher  import score_jobs
from notifier import send_email
from config   import APHP_JOBS_URL, MAX_OFFERS_IN_EMAIL


def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Démarrage")
    print("=" * 55)

    # ── 1. Scraping ──────────────────────────────────────────
    try:
        jobs = scrape_jobs(APHP_JOBS_URL, max_pages=5)
    except Exception as e:
        print(f"❌ Erreur de scraping : {e}")
        sys.exit(1)

    if not jobs:
        print("⚠️  Aucune offre trouvée. Vérifier le sélecteur CSS du scraper.")
        send_email([])   # Email vide pour signaler le problème
        sys.exit(0)

    # ── 2. Scoring avec Claude ───────────────────────────────
    try:
        scored_jobs = score_jobs(jobs)
    except Exception as e:
        print(f"❌ Erreur de scoring : {e}")
        sys.exit(1)

    # ── 3. Limiter au top N ──────────────────────────────────
    top_jobs = scored_jobs[:MAX_OFFERS_IN_EMAIL]

    # ── 4. Envoi de l'email ──────────────────────────────────
    send_email(top_jobs)

    print("\n" + "=" * 55)
    print(f"  ✅  Terminé — {len(top_jobs)} offre(s) envoyée(s)")
    print("=" * 55)


if __name__ == "__main__":
    main()