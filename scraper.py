import requests
from datetime import datetime
from html.parser import HTMLParser
from bs4 import BeautifulSoup

API_URL = "https://recrutement.aphp.fr/api/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Referer": "https://recrutement.aphp.fr/jobs",
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

def get_full_description(job_id: str) -> str:
    """Récupère la description complète depuis la page de l'offre."""
    try:
        url = f"https://recrutement.aphp.fr/jobs/{job_id}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        main = soup.find("main") or soup.find("article")
        if main:
            return main.get_text(separator=" ", strip=True)
    except Exception as e:
        print(f"    ⚠️  Erreur détail {job_id}: {e}")
    return ""

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

        for i, o in enumerate(offers):
            job_id = str(o.get("id", ""))
            print(f"    [{i+1}/{len(offers)}] Récupération détail {job_id}...")
            description = get_full_description(job_id)

            jobs.append({
                "id":          job_id,
                "title":       o.get("title") or o.get("name") or "Sans titre",
                "location":    o.get("location") or o.get("site") or "Non précisé",
                "description": description,
                "url":         f"https://recrutement.aphp.fr/jobs/{job_id}",
                "scraped_at":  datetime.now().isoformat(),
            })

        total = data.get("jobs", {}).get("totalCount", "?")
        print(f"  ✅ Page {page} OK — {len(jobs)} offres cumulées / {total} total")

    print(f"\n✅ Total scraped : {len(jobs)} offres")
    return jobs