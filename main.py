from scraper  import scrape_jobs
from database import init_db, upsert_jobs, get_stats
from config   import APHP_JOBS_URL

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Démarrage")
    print("=" * 55)

    init_db()
    jobs = scrape_jobs(APHP_JOBS_URL, max_pages=115)
    diff = upsert_jobs(jobs)

    stats = get_stats()
    print(f"\n📊 Stats DB :")
    print(f"   Total       : {stats['total']}")
    print(f"   Actives     : {stats['active']}")
    print(f"   Retirées    : {stats['removed']}")
    print(f"   🆕 Nouvelles : {len(diff['new'])}")
    print(f"   🗑️  Retirées  : {len(diff['removed'])}")

if __name__ == "__main__":
    main()