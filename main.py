import csv
from datetime import datetime
from scraper import scrape_jobs
from config import APHP_JOBS_URL

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Démarrage")
    print("=" * 55)

    # Scrape 1 seule page (20 offres) et on garde les 5 premières
    jobs = scrape_jobs(APHP_JOBS_URL, max_pages=1)
    jobs = jobs[:5]
    print(f"\n📋 {len(jobs)} offres récupérées pour le test\n")

    # Affichage
    for i, job in enumerate(jobs, 1):
        print(f"[{i}] {job['title']}")
        print(f"     📍 {job['location']}")
        print(f"     🔗 {job['url']}")
        print()

    # Export CSV
    filename = f"offres_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "title", "location", "url", "description", "scraped_at"])
        writer.writeheader()
        writer.writerows(jobs)

    print(f"✅ Résultats exportés dans : {filename}")

if __name__ == "__main__":
    main()