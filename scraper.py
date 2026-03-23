import requests
import random
import time
from datetime import datetime
from html.parser import HTMLParser

from notifier import send_telegram

# ─────────────────────────
# CONFIG
# ─────────────────────────
API_URL = "https://recrutement.aphp.fr/api/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Referer": "https://recrutement.aphp.fr/jobs",
}

TAG_IDS = {
    "434": "contrat",
    "435": "teletravail",
    "436": "metier",
    "437": "hopital",
    "584": "horaire",
    "585": "temps_travail",
}

session = requests.Session()

# ─────────────────────────
# UTILS
# ─────────────────────────
def notify(msg):
    print(msg)
    try:
        send_telegram(msg)
    except Exception as e:
        print(f"(Telegram failed: {e})")

class ScrapingError(Exception):
    pass

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
    result = {}
    for tag in custom_tags:
        key = TAG_IDS.get(str(tag.get("id")))
        if key:
            result[key] = tag.get("value", "")
    return result

# ─────────────────────────
# SESSION
# ─────────────────────────
def init_session():
    try:
        session.get(
            "https://recrutement.aphp.fr/jobs",
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=15
        )
        notify("✅ Session initialisée")
    except Exception as e:
        raise ScrapingError(f"Init session failed: {e}")

# ─────────────────────────
# FETCH (SMART RETRY)
# ─────────────────────────
def fetch_page(page: int, retries: int = 3) -> dict:
    payload = {
        "facets": {},
        "currentPage": page,
        "onlyCmsJobs": False,
        "loadOffers": True
    }

    for attempt in range(1, retries + 1):
        try:
            r = session.post(API_URL, json=payload, headers=HEADERS, timeout=20)

            # ✅ succès
            if r.status_code == 200:
                return r.json()

            # 🔁 retry seulement sur erreurs serveur
            if r.status_code >= 500:
                notify(f"⚠️ HTTP {r.status_code} page {page} (retry {attempt})")
            else:
                # 💥 erreur client → stop direct
                raise ScrapingError(f"HTTP {r.status_code} page {page}")

        except requests.exceptions.Timeout:
            notify(f"⏱️ Timeout page {page} ({attempt}/{retries})")

        except requests.exceptions.ConnectionError:
            notify(f"🔌 Connexion error page {page} ({attempt}/{retries})")

        # ⏳ backoff progressif (anti-ban)
        sleep_time = 2 * attempt + random.uniform(0.5, 1.5)
        time.sleep(sleep_time)

    # 💥 échec total
    raise ScrapingError(f"Page {page} failed after {retries} retries")

# ─────────────────────────
# MAIN SCRAPER
# ─────────────────────────
def scrape_jobs(url=None, max_pages=115) -> list[dict]:
    jobs = []

    notify("🚀 Début scraping")
    init_session()
    time.sleep(2)

    for page in range(1, max_pages + 1):

        notify(f"📄 Page {page}/{max_pages}")

        data = fetch_page(page)

        offers = data.get("jobs", {}).get("offers", [])

        # 💥 blocage détecté
        if not offers:
            raise ScrapingError(f"Aucune offre page {page} (blocage probable)")

        for o in offers:
            tags = parse_tags(o.get("customTags", []))

            jobs.append({
                "id":               str(o.get("id", "")),
                "title":            o.get("title", "Sans titre").strip(),
                "location":         o.get("location", "Non précisé"),
                "metier":           tags.get("metier", ""),
                "hopital":          tags.get("hopital", ""),
                "contrat":          tags.get("contrat", ""),
                "teletravail":      tags.get("teletravail", ""),
                "horaire":          tags.get("horaire", ""),
                "temps_travail":    tags.get("temps_travail", ""),
                "filiere":          o.get("jobCategoryLabel", ""),
                "date_publication": o.get("publicationDate", ""),
                "description":      strip_html(o.get("description", "")),
                "url":              f"https://recrutement.aphp.fr/jobs/{o.get('id', '')}",
                "scraped_at":       datetime.now().isoformat(),
            })

        total = data.get("jobs", {}).get("totalCount", "?")

        # 📊 log toutes les 5 pages
        if page % 5 == 0:
            notify(f"📊 {len(jobs)} offres cumulées / {total}")

        # ⚡ vitesse contrôlée (rapide mais safe)
        time.sleep(random.uniform(0.8, 1.5))

    notify(f"✅ Scraping terminé : {len(jobs)} offres")

    # 🛡️ sécurité anti faux positif
    if len(jobs) < 2000:
        raise ScrapingError(f"Scraping incomplet : {len(jobs)} offres")

    return jobs