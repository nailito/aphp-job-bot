import csv
from datetime import datetime
from scraper import scrape_jobs
from config import APHP_JOBS_URL

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Démarrage")
    print("=" * 55)

    # Scrape 1 seule page et on garde les 5 premières offres
    jobs = scrape_jobs(APHP_JOBS_URL, max_pages=1)
    jobs = jobs[:5]
    print(f"\n📋 {len(jobs)} offres récupérées pour le test\n")

    # Affichage
    for i, job in enumerate(jobs, 1):
        print(f"[{i}] {job['title']}")
        print(f"     🩺 {job['metier']} — {job['filiere']}")
        print(f"     🏥 {job['hopital']}")
        print(f"     📍 {job['location']}")
        print(f"     📄 {job['contrat']} | ⏱ {job['temps_travail']} | 🖥 {job['teletravail']}")
        print(f"     🔗 {job['url']}")
        print()

    # Export CSV
    filename = f"offres_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = [
        "id", "title", "metier", "filiere", "hopital", "location",
        "contrat", "teletravail", "horaire", "temps_travail",
        "date_publication", "url", "description", "scraped_at"
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)

    print(f"✅ Résultats exportés dans : {filename}")

if __name__ == "__main__":
    main()