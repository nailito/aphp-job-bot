import csv
from collections import Counter
from scraper import scrape_jobs
from config import APHP_JOBS_URL

def main():
    print("📊 Analyse des offres APHP en cours...")

    # Scrape toutes les pages
    jobs = scrape_jobs(APHP_JOBS_URL, max_pages=115)

    # Compter les occurrences par métier + filière
    metier_count   = Counter(j.get("metier", "Non précisé")  for j in jobs)
    filiere_count  = Counter(j.get("filiere", "Non précisé") for j in jobs)

    # Affichage métiers triés par fréquence
    print(f"\n{'='*60}")
    print(f"  📋 {len(jobs)} offres | {len(metier_count)} métiers distincts")
    print(f"{'='*60}")
    print(f"\n🩺 MÉTIERS (triés par fréquence) :\n")
    for metier, count in metier_count.most_common():
        bar = "█" * min(count // 10, 40)
        print(f"  {count:4d}  {bar} {metier}")

    print(f"\n🏥 FILIÈRES (triées par fréquence) :\n")
    for filiere, count in filiere_count.most_common():
        bar = "█" * min(count // 10, 40)
        print(f"  {count:4d}  {bar} {filiere}")

    # Export CSV pour analyse dans Excel
    with open("analyse_metiers.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metier", "filiere", "count_metier", "title", "url"])
        for job in sorted(jobs, key=lambda x: x.get("metier", "")):
            writer.writerow([
                job.get("metier", ""),
                job.get("filiere", ""),
                metier_count[job.get("metier", "")],
                job.get("title", ""),
                job.get("url", ""),
            ])

    print(f"\n✅ Export CSV : analyse_metiers.csv")
    print(f"\n💡 Utilise ce fichier pour identifier les métiers à ajouter dans EXCLUDED_METIERS dans config.py")

if __name__ == "__main__":
    main()