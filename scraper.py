import requests
from datetime import datetime
from html.parser import HTMLParser

API_URL = "https://recrutement.aphp.fr/api/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Referer": "https://recrutement.aphp.fr/jobs",
}

# Correspondance des IDs de customTags
TAG_IDS = {
    "434": "contrat",
    "435": "teletravail",
    "436": "metier",
    "437": "hopital",
    "584": "horaire",
    "585": "temps_travail",
}

def strip_html(html: str) -> str:
    class MLStripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.fed = []
        def handle_data(self, d):
            self.fed.append(d)
        def get_data(self):
            return " ".join(self.fed)
    s = MLStripper()
    s.feed(html or "")
    return s.get_data().strip()

def parse_tags(custom_tags: list) -> dict:
    """Extrait les champs utiles depuis les customTags."""
    result = {}
    for tag in custom_tags:
        key = TAG_IDS.get(str(tag.get("id")))
        if key:
            result[key] = tag.get("value", "")
    return result

def scrape_jobs(url=None, max_pages=5) -> list[dict]:
    jobs = []

    for page in range(1, max_pages + 1):
        print(f"  📄 Page {page}...")

        payload = {
            "facets": {},
            "currentPage": page,
            "onlyCmsJobs": False,
            "loadOffers": True
        }

        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=15)

        if r.status_code != 200:
            print(f"  ⚠️  Erreur HTTP {r.status_code}")
            break

        data = r.json()
        offers = data.get("jobs", {}).get("offers", [])

        if not offers:
            print("  ✅ Plus d'offres.")
            break

        for o in offers:
            tags = parse_tags(o.get("customTags", []))
            jobs.append({
                "id":           str(o.get("id", "")),
                "title":        o.get("title", "Sans titre").strip(),
                "location":     o.get("location", "Non précisé"),
                "metier":       tags.get("metier", ""),
                "hopital":      tags.get("hopital", ""),
                "contrat":      tags.get("contrat", ""),
                "teletravail":  tags.get("teletravail", ""),
                "horaire":      tags.get("horaire", ""),
                "temps_travail":tags.get("temps_travail", ""),
                "filiere":      o.get("jobCategoryLabel", ""),
                "date_publication": o.get("publicationDate", ""),
                "description":  strip_html(o.get("description", "")),
                "url":          f"https://recrutement.aphp.fr/jobs/{o.get('id', '')}",
                "scraped_at":   datetime.now().isoformat(),
            })

        total = data.get("jobs", {}).get("totalCount", "?")
        print(f"  ✅ {len(offers)} offres récupérées (total dispo : {total})")

    print(f"\n✅ Total scraped : {len(jobs)} offres")
    return jobs