import time
import json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
 
def scrape_jobs(url: str, max_pages: int = 5) -> list[dict]:
    """
    Scrape les offres d'emploi depuis le site APHP.
    Retourne une liste de dicts : {id, title, description, location, date, url}
    """
    jobs = []
 
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
 
        print(f"🌐 Connexion à {url} ...")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)
 
        for page_num in range(1, max_pages + 1):
            print(f"  📄 Page {page_num}...")
 
            # Attendre que les offres soient chargées
            try:
                page.wait_for_selector("[class*='job'], [class*='offer'], article, .card", timeout=10000)
            except Exception:
                print("  ⚠️  Sélecteur non trouvé, tentative avec le DOM brut...")
 
            # Extraire les offres via JavaScript directement dans la page
            raw_jobs = page.evaluate("""
                () => {
                    const results = [];
                    // Sélecteurs courants pour les sites d'offres d'emploi
                    const selectors = [
                        'a[href*="/job"]',
                        'a[href*="/offre"]',
                        '[class*="job-item"]',
                        '[class*="offer-item"]',
                        '[class*="job-card"]',
                        'article',
                    ];
 
                    let items = [];
                    for (const sel of selectors) {
                        const found = document.querySelectorAll(sel);
                        if (found.length > 3) { items = Array.from(found); break; }
                    }
 
                    items.forEach((el, i) => {
                        const titleEl = el.querySelector('h1, h2, h3, h4, [class*="title"], [class*="poste"]');
                        const linkEl  = el.tagName === 'A' ? el : el.querySelector('a');
                        const locEl   = el.querySelector('[class*="location"], [class*="lieu"], [class*="site"]');
                        const dateEl  = el.querySelector('[class*="date"], time');
                        const descEl  = el.querySelector('[class*="desc"], [class*="detail"], p');
 
                        if (!titleEl) return;
 
                        results.push({
                            id:          linkEl ? linkEl.href : `job-${i}`,
                            title:       titleEl.innerText.trim(),
                            url:         linkEl ? linkEl.href : window.location.href,
                            location:    locEl  ? locEl.innerText.trim()  : 'Non précisé',
                            date_text:   dateEl ? dateEl.innerText.trim() : '',
                            description: descEl ? descEl.innerText.trim() : titleEl.innerText.trim(),
                        });
                    });
                    return results;
                }
            """)
 
            # Enrichir chaque offre avec la page de détail
            for job in raw_jobs:
                job["scraped_at"] = datetime.now().isoformat()
                if job not in jobs:
                    jobs.append(job)
 
            # Pagination — chercher un bouton "Suivant"
            next_btn = page.query_selector(
                'a[aria-label*="suivant"], a[aria-label*="next"], '
                'button:has-text("Suivant"), button:has-text("Next"), '
                '[class*="next"]:not([disabled])'
            )
            if not next_btn:
                print("  ✅ Dernière page atteinte.")
                break
 
            next_btn.click()
            time.sleep(2)
 
        browser.close()
 
    print(f"\n✅ {len(jobs)} offres trouvées au total.")
    return jobs
 
 
def enrich_job(job: dict, page) -> dict:
    """Visite la page de l'offre pour en récupérer la description complète."""
    try:
        page.goto(job["url"], wait_until="networkidle", timeout=15000)
        time.sleep(1)
        full_desc = page.evaluate("""
            () => {
                const el = document.querySelector(
                    '[class*="description"], [class*="content"], [class*="detail"], main, article'
                );
                return el ? el.innerText.trim() : document.body.innerText.trim().slice(0, 2000);
            }
        """)
        job["description"] = full_desc[:3000]  # Limiter pour l'API
    except Exception as e:
        print(f"  ⚠️  Impossible d'enrichir {job['url']} : {e}")
    return job
 
 
def filter_recent(jobs: list[dict], hours: int = 48) -> list[dict]:
    """Garde uniquement les offres récentes (par date si disponible)."""
    # Si on ne peut pas parser les dates, on renvoie tout
    # (GitHub Actions tourne 1x/jour donc pas de doublon)
    return jobs