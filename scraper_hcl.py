"""
scraper_hcl.py
Scrape toutes les offres d'emploi des Hospices Civils de Lyon (HCL)
via l'API REST WordPress native — publique, sans authentification.

Endpoint : GET https://chu-lyon.nous-recrutons.fr/wp-json/wp/v2/job
Paramètres : ?per_page=100&page=N&order=desc&orderby=date

Flux :
  1. Pagination GET paginée → liste complète des offres (toutes métadonnées incluses)
  2. Résolution des labels de taxonomie (avec cache en mémoire)
  3. Enrichissement : description complète extraite de content.rendered (nouvelles offres seulement)

Aucun fetch de page individuelle nécessaire : tout est dans l'API.
"""

import logging
import time
from html import unescape

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://chu-lyon.nous-recrutons.fr"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"
JOB_ENDPOINT = f"{API_BASE}/job"

PER_PAGE = 100          # max autorisé par l'API WP REST
SLEEP_BETWEEN_PAGES = 0.3  # secondes de politesse inter-pages

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Noms des taxonomies tels qu'ils apparaissent dans la réponse API WP REST.
# Clé = nom du champ dans offer dict cible, valeur = nom de la taxonomie WP.
TAXONOMY_MAP = {
    "contrats":    "job_custom_chulyon_typedecontrat",  # type(s) de contrat
    "localisation": "job_custom_hcl_hopital",           # hôpital / site
    "filiere":     "job_custom_hcl_filiere",            # filière métier (non stocké seul, injecté dans description)
}

# Cache des labels de taxonomie pour éviter les appels répétés
# Structure : { taxonomy_slug: { term_id: label } }
_taxonomy_cache: dict[str, dict[int, str]] = {}


# ---------------------------------------------------------------------------
# Résolution des taxonomies
# ---------------------------------------------------------------------------

def resolve_term_labels(
    session: requests.Session,
    taxonomy: str,
    term_ids: list[int],
) -> list[str]:
    """
    Résout une liste d'IDs de termes taxonomy en labels texte.
    Utilise le cache en mémoire ; fait un appel API uniquement pour les IDs manquants.

    Args:
        session:   session requests réutilisable
        taxonomy:  slug de la taxonomie WP (ex: "job_custom_hcl_hopital")
        term_ids:  liste d'IDs à résoudre

    Returns:
        Liste de labels (strings). Si la résolution échoue, retourne les IDs en string.
    """
    if not term_ids:
        return []

    cache = _taxonomy_cache.setdefault(taxonomy, {})
    missing_ids = [tid for tid in term_ids if tid not in cache]

    if missing_ids:
        ids_param = ",".join(str(i) for i in missing_ids)
        url = f"{API_BASE}/{taxonomy}"
        try:
            resp = session.get(
                url,
                params={"include": ids_param, "per_page": 100},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            for term in resp.json():
                tid = term.get("id")
                name = term.get("name", "")
                if tid:
                    cache[tid] = unescape(name).strip()
        except Exception as e:
            logger.warning(
                f"Résolution taxonomy '{taxonomy}' échouée pour IDs {missing_ids} : {e}"
            )
            # Fallback : stocker les IDs bruts comme labels
            for tid in missing_ids:
                cache.setdefault(tid, str(tid))

    return [cache.get(tid, str(tid)) for tid in term_ids]


# ---------------------------------------------------------------------------
# Nettoyage HTML
# ---------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """
    Convertit du HTML en texte propre via BeautifulSoup.
    Supprime les balises, décode les entités, nettoie les espaces.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Remplace les <br> et <p> par des sauts de ligne pour conserver la structure
    for tag in soup.find_all(["br", "p", "li", "h1", "h2", "h3", "h4"]):
        tag.insert_before("\n")
    text = soup.get_text(separator=" ", strip=False)
    # Nettoie les espaces multiples et lignes vides consécutives
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def build_description(offer_raw: dict) -> str:
    """
    Construit la description complète à partir des champs disponibles :
    - content.rendered (corps principal)
    - meta.job_offer_mission
    - meta.job_offer_profile

    Retourne un texte propre sans HTML.
    """
    parts = []

    content_html = offer_raw.get("content", {}).get("rendered", "")
    content_text = html_to_text(content_html)
    if content_text:
        parts.append(content_text)

    meta = offer_raw.get("meta", {}) or {}

    mission = str(meta.get("job_offer_mission") or "").strip()
    if mission:
        parts.append(f"Mission :\n{html_to_text(mission)}")

    profile = str(meta.get("job_offer_profile") or "").strip()
    if profile:
        parts.append(f"Profil recherché :\n{html_to_text(profile)}")

    return "\n\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Parsing d'une offre individuelle
# ---------------------------------------------------------------------------

def parse_offer(
    session: requests.Session,
    raw: dict,
    known_ids: set[int],
) -> dict:
    """
    Transforme un objet JSON brut de l'API WP REST en dict normalisé
    compatible avec database_hcl.upsert_jobs.

    Args:
        session:   session requests (pour la résolution des taxonomies)
        raw:       dict JSON brut retourné par l'API
        known_ids: IDs déjà présents en base

    Returns:
        Dict avec les champs : id, titre, url, localisation, contrats,
        duree, date_debut, description (None si offre déjà connue).
    """
    offer_id = raw["id"]

    # --- Titre
    titre = html_to_text(raw.get("title", {}).get("rendered", "")).strip()

    # --- URL
    url = raw.get("link", "")

    # --- Taxonomies : localisation (hôpital)
    hopital_ids = raw.get(TAXONOMY_MAP["localisation"], []) or []
    localisation_labels = resolve_term_labels(session, TAXONOMY_MAP["localisation"], hopital_ids)
    localisation = ", ".join(localisation_labels)

    # --- Taxonomies : types de contrat
    # L'API peut exposer la taxonomie sous plusieurs noms selon la config WP.
    # On essaie les deux champs connus.
    contrat_ids = (
        raw.get(TAXONOMY_MAP["contrats"], [])
        or raw.get("job_contract_type", [])
        or []
    )
    contrat_labels = resolve_term_labels(session, TAXONOMY_MAP["contrats"], contrat_ids)
    # Fallback sur job_contract_type si le premier endpoint échoue
    if not contrat_labels and raw.get("job_contract_type"):
        contrat_labels = resolve_term_labels(
            session, "job_contract_type", raw["job_contract_type"]
        )
    contrats = ", ".join(contrat_labels)

    # --- Filière (injectée dans la description si présente, pas colonne dédiée)
    filiere_ids = raw.get(TAXONOMY_MAP["filiere"], []) or []
    filiere_labels = resolve_term_labels(session, TAXONOMY_MAP["filiere"], filiere_ids)
    filiere = ", ".join(filiere_labels)

    # --- Meta
    meta = raw.get("meta", {}) or {}
    duree = str(meta.get("job_offer_duration") or "").strip()
    date_debut = str(meta.get("job_creation_date") or "").strip()

    # --- Description (uniquement pour les nouvelles offres)
    # parse_offer() — remplacer le bloc description

    # --- Description (uniquement pour les nouvelles offres)
    if offer_id not in known_ids:
        description = build_description(raw)
        # SUPPRIMÉ : l'injection "Filière : {filiere}\n\n" dans la description
    else:
        description = None

    return {
        "id": offer_id,
        "titre": titre,
        "url": url,
        "localisation": localisation,
        "contrats": contrats,
        "filiere": filiere,         
        "duree": duree,
        "date_debut": date_debut,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Pagination de l'API
# ---------------------------------------------------------------------------

def fetch_all_offers_raw(session: requests.Session) -> list[dict]:
    """
    Pagine l'API REST WP jusqu'à épuisement.
    Retourne la liste complète des objets JSON bruts.
    """
    all_raw = []
    page = 1

    while True:
        logger.info(f"Fetching page {page}...")
        try:
            resp = session.get(
                JOB_ENDPOINT,
                params={
                    "per_page": PER_PAGE,
                    "page": page,
                    "order": "desc",
                    "orderby": "date",
                    # Demande les champs meta dans la réponse
                    "_fields": (
                        "id,date,link,title,content,meta,"
                        "job_custom_chulyon_typedecontrat,"
                        "job_custom_hcl_filiere,"
                        "job_custom_hcl_hopital,"
                        "job_contract_type"
                    ),
                },
                headers=HEADERS,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"Erreur réseau page {page} : {e}")
            break

        # 400 ou 404 avec code rest_post_invalid_page_number = fin normale
        if resp.status_code in (400, 404):
            logger.info(f"Page {page} hors limites (HTTP {resp.status_code}) — fin pagination.")
            break

        resp.raise_for_status()

        batch = resp.json()
        if not batch:
            logger.info(f"Page {page} vide — fin pagination.")
            break

        all_raw.extend(batch)
        total = resp.headers.get("X-WP-Total", "?")
        logger.info(f"Page {page} : {len(batch)} offres ({len(all_raw)}/{total} total)")

        # Moins d'offres que le max → dernière page
        if len(batch) < PER_PAGE:
            break

        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)

    return all_raw


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def run_scraper(known_ids: set[int]) -> list[dict]:
    """
    Lance le scraping complet HCL via l'API REST WordPress.

    Args:
        known_ids: ensemble des IDs déjà présents en base Supabase.
                   Utilisé pour éviter de re-générer la description
                   des offres existantes.

    Returns:
        Liste de dicts normalisés, prêts pour database_hcl.upsert_jobs.
        Champs : id, titre, url, localisation, contrats, duree, date_debut, description.
        description = None pour les offres déjà connues.
    """
    session = requests.Session()
    logger.info("=== Scraper HCL (API REST) — démarrage ===")

    import time as _time
    start = _time.time()

    # Phase 1 : récupération de toutes les offres brutes
    raw_offers = fetch_all_offers_raw(session)
    logger.info(f"{len(raw_offers)} offres brutes récupérées depuis l'API.")

    # Phase 2 : parsing + résolution des taxonomies
    offers = []
    for raw in raw_offers:
        try:
            offer = parse_offer(session, raw, known_ids)
            offers.append(offer)
        except Exception as e:
            logger.warning(f"Erreur parsing offre id={raw.get('id')} : {e}")

    elapsed = _time.time() - start
    new_count = sum(1 for o in offers if o["id"] not in known_ids)
    logger.info(
        f"=== Scraper HCL terminé en {elapsed:.1f}s — "
        f"{len(offers)} offres dont {new_count} nouvelles ==="
    )

    return offers


# ---------------------------------------------------------------------------
# Exécution directe (debug)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    results = run_scraper(known_ids=set())
    print(f"\n{len(results)} offres scrapées.")
    if results:
        print("\nExemple (première offre) :")
        ex = results[0]
        for k, v in ex.items():
            val = (str(v)[:200] + "...") if v and len(str(v)) > 200 else (v or "(vide)")
            print(f"  {k:15} : {val}")