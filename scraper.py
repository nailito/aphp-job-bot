import requests
import random
import time
import math
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from notifier import send_telegram

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

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
last_message_id  = None


def send_or_edit(message: str):
    global last_message_id

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return

    try:
        if last_message_id is None:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message}
            )
            last_message_id = r.json()["result"]["message_id"]
        else:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "message_id": last_message_id,
                    "text": message
                }
            )
    except Exception as e:
        print(f"Telegram error: {e}")


def progress_bar(current, total, length=20):
    ratio = current / total if total else 0
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)


def notify(msg):
    print(msg)
    try:
        send_telegram(msg)
    except Exception as e:
        print(f"(Telegram failed: {e})")


class ScrapingError(Exception):
    pass


# ─────────────────────────
# UTILS
# ─────────────────────────
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


def extract_reference(description: str) -> str | None:
    if not description:
        return None

    text = strip_html(description)
    match = re.search(r"Référence de l'offre\s*([0-9\-]+)", text)

    if match:
        return match.group(1).strip()

    return None


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
    except Exception as e:
        raise ScrapingError(f"Init session failed: {e}")


# ─────────────────────────
# FETCH
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

            if r.status_code == 200:
                return r.json()

            if r.status_code >= 500:
                notify(f"⚠️ HTTP {r.status_code} page {page} (retry {attempt})")
            else:
                raise ScrapingError(f"HTTP {r.status_code} page {page}")

        except requests.exceptions.Timeout:
            notify(f"⏱️ Timeout page {page} ({attempt})")

        except requests.exceptions.ConnectionError:
            notify(f"🔌 Connexion error page {page} ({attempt})")

        time.sleep(2 * attempt + random.uniform(0.5, 1.5))

    raise ScrapingError(f"Page {page} failed after retries")


# ─────────────────────────
# SCRAPER
# ─────────────────────────
def scrape_jobs(url=None, max_pages=115) -> list[dict]:
    jobs = []
    seen_ids = set()
    page_stats = []

    skipped_no_id = 0
    skipped_error = 0
    with_ref = 0
    without_ref = 0

    send_or_edit("🚀 Initialisation du scraping...")

    init_session()
    time.sleep(2)

    first_page = fetch_page(1)
    total_jobs = first_page.get("jobs", {}).get("totalCount", 0)
    offers_first = first_page.get("jobs", {}).get("offers", [])
    jobs_per_page = len(offers_first)

    if jobs_per_page == 0:
        raise ScrapingError("Aucune offre page 1")

    total_pages = math.ceil(total_jobs / jobs_per_page)
    start_time = time.time()

    for page in range(1, min(total_pages, max_pages) + 1):

        try:
            data = first_page if page == 1 else fetch_page(page)
            offers = data.get("jobs", {}).get("offers", [])

            page_stats.append((page, len(offers)))
            print(f"[DEBUG] PAGE {page} → {len(offers)} offres")

            for o in offers:
                try:
                    raw_id = o.get("id")

                    if raw_id is None:
                        skipped_no_id += 1
                        continue

                    job_id = str(raw_id)  # ← format original

                    ref = extract_reference(description)
                    if ref:
                        with_ref += 1
                    else:
                        without_ref += 1

                        if raw_id is None:
                            fallback = f"{o.get('title','')}_{o.get('location','')}"
                            job_id = f"FALLBACK_{hash(fallback)}"
                            skipped_no_id += 1
                        else:
                            job_id = f"ID_{raw_id}"

                    if job_id in seen_ids:
                        continue

                    tags = parse_tags(o.get("customTags", []))

                    job = {
                        "id":               job_id,
                        "reference":        ref,
                        "title":            (o.get("title") or "Sans titre").strip(),
                        "location":         o.get("location") or "Non précisé",
                        "metier":           tags.get("metier", ""),
                        "hopital":          tags.get("hopital", ""),
                        "contrat":          tags.get("contrat", ""),
                        "teletravail":      tags.get("teletravail", ""),
                        "horaire":          tags.get("horaire", ""),
                        "temps_travail":    tags.get("temps_travail", ""),
                        "filiere":          o.get("jobCategoryLabel") or "",
                        "date_publication": o.get("publicationDate") or "",
                        "description":      strip_html(description),
                        "url":              f"https://recrutement.aphp.fr/jobs/{raw_id or ''}",
                        "scraped_at":       datetime.now().isoformat(),
                    }

                    jobs.append(job)
                    seen_ids.add(job_id)

                except Exception as e:
                    skipped_error += 1
                    print(f"[ERROR_JOB] {e}")
                    continue

        except Exception as e:
            notify(f"⚠️ Erreur page {page}: {e}")
            raise

        elapsed = int(time.time() - start_time)
        speed = page / (elapsed / 60 + 0.01)

        bar = progress_bar(page, total_pages)
        percent = int((page / total_pages) * 100)

        message = f"""
🚀 Scraping APHP

{bar} {percent}%
📄 Page {page} / {total_pages}
📊 {len(jobs)} / {total_jobs} offres

⏱️ {elapsed}s | ⚡ {speed:.1f} pages/min
"""

        if page % 2 == 0 or page == total_pages:
            send_or_edit(message)

        time.sleep(random.uniform(0.8, 1.5))

    elapsed = int(time.time() - start_time)

    send_or_edit(f"""
✅ Scraping terminé

📊 {len(jobs)} offres récupérées
⏱️ {elapsed}s

📌 Avec ref: {with_ref}
📌 Sans ref: {without_ref}

⚠️ skipped no id: {skipped_no_id}
⚠️ skipped error: {skipped_error}
""")

    print(f"[DEBUG] with_ref={with_ref}")
    print(f"[DEBUG] without_ref={without_ref}")

    return jobs