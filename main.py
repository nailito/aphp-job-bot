import csv
from datetime import datetime
from scraper import scrape_jobs
from matcher import score_jobs
from config import APHP_JOBS_URL, EXCLUDED_METIERS

def main():
    print("=" * 55)
    print("  🏥  Bot de veille APHP - Démarrage")
    print("=" * 55)

    # Scraping toutes les pages (2288 offres / 20 par page = ~115 pages)
    jobs = scrape_jobs(APHP_JOBS_URL, max_pages=115)

    # Filtre métiers exclus
    avant = len(jobs)
    jobs = [j for j in jobs if j.get("metier", "") not in EXCLUDED_METIERS]
    print(f"\n🚫 {avant - len(jobs)} offres filtrées par métier, {len(jobs)} restantes")

    # Scoring LLM
    scored = score_jobs(jobs)

    # Affichage résumé
    print("\n📋 Top 10 :\n")
    for i, job in enumerate(scored[:10], 1):
        print(f"[{i}] {job['score']}/100 — {job['title']}")
        print(f"     🏥 {job['hopital']} | 📍 {job['location']}")
        print(f"     🔗 {job['url']}")
        print()

    # Export CSV
    filename = f"matching_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = [
        "score", "title", "metier", "filiere", "hopital", "location",
        "contrat", "teletravail", "mots_cles_matches", "raison",
        "date_publication", "url"
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored)

    print(f"\n✅ {len(scored)} offres exportées dans : {filename}")

if __name__ == "__main__":
    main()