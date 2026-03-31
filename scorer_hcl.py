"""
scorer_hcl.py
Scoring des offres HCL ayant passé le filtre IA.

Miroir de scorer.py (APHP), adapté à :
  - la structure hcl_jobs (titre, localisation, contrats, filiere…)
  - la connexion injectée (conn en paramètre)
  - update_score(conn, job_id, score, analysis) de database_hcl
  - retour d'un dict stats (attendu par pipeline_hcl.py)
"""

import json
import logging
import os
import re
import time

from groq import Groq

from config import GROQ_API_KEY, PROFILE_FACTUEL, PROFILE_MOTIVATIONNEL
from database_hcl import get_offers_to_score, update_score

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

PROMPT_TEMPLATE = """
Tu es un recruteur senior aux Hospices Civils de Lyon (HCL). Tu reçois le CV d'un candidat et une offre d'emploi.
Ton rôle est d'évaluer honnêtement si ce candidat serait retenu ou écarté pour ce poste.
Tu dois être critique et identifier les vrais points de friction, pas juste les similitudes.

## PROFIL FACTUEL DU CANDIDAT
{profile_factuel}

## CE QUE RECHERCHE LE CANDIDAT
{profile_motivationnel}

## OFFRE À ÉVALUER
Titre        : {titre}
Filière      : {filiere}
Localisation : {localisation}
Contrat      : {contrats}
Description  : {description}

## INSTRUCTIONS

En tant que recruteur HCL, évalue :

1. **Est-ce que tu retiendrais ce CV pour ce poste ?**
   Sois honnête sur les points éliminatoires potentiels :
   - Manque d'expérience hospitalière française ?
   - Niveau trop junior pour les responsabilités demandées ?
   - Compétences techniques manquantes ?
   - Profil trop technique pour un poste administratif (ou inversement) ?

2. **Est-ce que ce poste correspond aux aspirations du candidat ?**
   Croise avec ce qu'il recherche :
   - Missions concrètes et bien définies ?
   - Dimension analytique présente ?
   - Contact terrain avec équipes soignantes ?
   - Potentiel d'évolution ?

3. **Score et priorité**
   - P1 (score >= 80) : excellent match des deux côtés, peu de friction
   - P2 (score 60-79) : bon potentiel mais points à vérifier en entretien
   - P3 (score 40-59) : match partiel, risque réel de rejet ou de déception
   - En dessous de 40 : ne pas recommander

## RÈGLES DE RÉDACTION — OBLIGATOIRES

⚠️ Il est STRICTEMENT INTERDIT de commencer la raison par une phrase générique comme :
"Le candidat possède des compétences solides", "Le profil est pertinent",
"Le candidat présente une expérience intéressante" ou toute formule similaire.

La raison DOIT :
- Mentionner des éléments SPÉCIFIQUES à cette offre (nom du service, outil précis demandé,
  type de mission exact, niveau d'expérience requis, etc.)
- Identifier le VRAI point de friction pour CE poste (pas une friction générique)
- Conclure avec un verdict recruteur tranché (retenu / écarté / borderline avec réserve)

Structure attendue pour "raison" :
- Phrase 1 : ce qui colle spécifiquement entre le profil et CETTE offre
  (cite un élément concret de la description de l'offre)
- Phrase 2 : le vrai point de friction ou risque de rejet pour CE poste précis
- Phrase 3 : verdict recruteur honnête et tranché

Réponds UNIQUEMENT en JSON valide, sans Markdown, sans texte avant ou après :
{{
  "score": <0-100>,
  "priorite": "P1" | "P2" | "P3",
  "raison": "<Phrase 1 spécifique à l'offre>. <Phrase 2 point de friction réel>. <Phrase 3 verdict tranché>",
  "points_forts": ["<point spécifique à cette offre 1>", "<point spécifique 2>"],
  "points_faibles": ["<point éliminatoire potentiel spécifique 1>", "<point spécifique 2>"]
}}
"""


# ─────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────

def _score_job(job: dict, client: Groq) -> dict | None:
    """
    Appelle le LLM et retourne le dict résultat parsé,
    ou None si toutes les tentatives ont échoué.
    Lève RuntimeError si la limite journalière Groq est atteinte.
    """
    prompt = PROMPT_TEMPLATE.format(
        profile_factuel=PROFILE_FACTUEL,
        profile_motivationnel=PROFILE_MOTIVATIONNEL,
        titre=job.get("titre", ""),
        filiere=job.get("filiere", ""),
        localisation=job.get("localisation", ""),
        contrats=job.get("contrats", ""),
        description=(job.get("description") or "")[:2000],
    )

    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            raw = response.choices[0].message.content.strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError(f"Pas de JSON trouvé : {raw[:80]}")

            result = json.loads(match.group(0))
            result["raison"] = result.get("raison", "").strip() or "Pas de justification fournie"
            return result

        except Exception as e:
            err = str(e)
            logger.warning(f"    Tentative {attempt + 1}/5 échouée : {err[:80]}")

            if "429" in err or "rate_limit" in err:
                if "per day" in err or "TPD" in err:
                    raise RuntimeError(f"Limite journalière Groq atteinte : {err}") from e
                logger.info("    Rate limit minute — pause 60s")
                time.sleep(60)
            else:
                break  # Erreur non-rate-limit : inutile de retenter

    return None


def _persist(conn, job: dict, result: dict):
    """Sérialise l'analyse complète et appelle update_score."""
    score = int(result.get("score", 0))
    analysis = json.dumps(
        {
            "priorite": result.get("priorite", "P3"),
            "raison": result.get("raison", ""),
            "points_forts": result.get("points_forts", []),
            "points_faibles": result.get("points_faibles", []),
        },
        ensure_ascii=False,
    )
    update_score(conn, job["id"], score, analysis)
    return score


def _notify_top_score(job: dict, score: int, priorite: str, raison: str):
    if score < 80:
        return
    try:
        from notifier import send_telegram
        send_telegram(
            f"🎯 <b>HCL [{priorite}] — {score}/100</b>\n"
            f"📋 {job.get('titre', '')}\n"
            f"📍 {job.get('localisation', '')}\n"
            f"🔗 {job.get('url', '')}"
        )
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

def run_scorer(conn, limit: int = None) -> dict:
    """
    Score les offres HCL ayant passé le filtre IA (score IS NULL).

    Paramètres
    ----------
    conn    : connexion psycopg active (injectée par pipeline_hcl.py)
    limit   : nombre max d'offres à traiter (debug)

    Retourne
    --------
    dict avec les clés : total, scored, errors, skipped
    """
    stats = {"total": 0, "scored": 0, "errors": 0, "skipped": 0}

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY manquante — scoring annulé")
        return stats

    client = Groq(api_key=GROQ_API_KEY)

    jobs = get_offers_to_score(conn)
    if limit:
        jobs = jobs[:limit]

    stats["total"] = len(jobs)
    logger.info(f"🎯 Scoring HCL — {len(jobs)} offres à évaluer")

    if not jobs:
        return stats

    daily_limit_hit = False

    for i, job in enumerate(jobs, 1):
        titre = (job.get("titre") or "")[:60]
        logger.info(f"  [{i}/{len(jobs)}] {titre}")

        if daily_limit_hit:
            stats["skipped"] += 1
            continue

        try:
            result = _score_job(job, client)

            if result is None:
                logger.warning(f"    ⚠️  Score impossible pour {job['id']}")
                stats["errors"] += 1
                continue

            score = _persist(conn, job, result)
            priorite = result.get("priorite", "P3")
            raison = result.get("raison", "")

            stats["scored"] += 1
            logger.info(f"    🎯 {priorite} — {score}/100 : {raison[:80]}")

            _notify_top_score(job, score, priorite, raison)

        except RuntimeError as e:
            # Limite Groq journalière : on arrête proprement sans planter
            logger.error(f"Limite Groq TPD : {e}")
            daily_limit_hit = True
            stats["skipped"] += 1

        except Exception as e:
            logger.error(f"    ⚠️  Erreur inattendue sur job {job['id']} : {e}")
            stats["errors"] += 1

    logger.info(
        f"✅ Scoring HCL terminé — "
        f"{stats['scored']} scorées | "
        f"{stats['errors']} erreurs | "
        f"{stats['skipped']} ignorées (limite Groq)"
    )
    return stats


# ─────────────────────────────────────────────
# DEBUG LOCAL
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from database_hcl import get_connection

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = get_connection(DATABASE_URL)
    try:
        stats = run_scorer(conn, limit=10)
        print(stats)
    finally:
        conn.close()