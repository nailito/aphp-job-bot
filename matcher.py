# ============================================================
#  matcher.py  —  Scoring des offres avec Claude (Anthropic)
# ============================================================
import json
import time
import anthropic
from config import ANTHROPIC_API_KEY, PROFILE, MIN_SCORE


def score_jobs(jobs: list[dict]) -> list[dict]:
    """
    Envoie chaque offre à Claude pour évaluer sa pertinence par rapport au profil.
    Retourne les offres enrichies d'un score et d'une justification, triées par score.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("❌ ANTHROPIC_API_KEY manquante dans les variables d'environnement !")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    scored = []

    print(f"\n🤖 Analyse de {len(jobs)} offres avec Claude...")

    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job.get('title', 'Sans titre')[:60]}...")

        prompt = f"""
Tu es un assistant de recrutement expert. Analyse l'adéquation entre ce profil candidat et cette offre d'emploi.

## PROFIL DU CANDIDAT
{PROFILE}

## OFFRE D'EMPLOI
Titre      : {job.get('title', 'N/A')}
Lieu       : {job.get('location', 'N/A')}
Description: {job.get('description', 'N/A')[:2000]}

## INSTRUCTIONS
Réponds UNIQUEMENT en JSON valide, sans balises Markdown, avec exactement ce format :
{{
  "score": <entier de 0 à 10>,
  "resume": "<1 phrase résumant l'offre>",
  "points_forts": ["<point 1>", "<point 2>"],
  "points_faibles": ["<point 1>"],
  "verdict": "<2-3 phrases expliquant le score>"
}}

Critères de scoring :
- 9-10 : Correspondance quasi parfaite
- 7-8  : Très bonne correspondance, quelques petits écarts
- 5-6  : Correspondance partielle, plusieurs points à vérifier
- 3-4  : Peu adapté mais pas impossible
- 0-2  : Inadapté au profil
"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            raw = response.content[0].text.strip()
            # Nettoyage au cas où Claude renvoie des backticks malgré la consigne
            raw = raw.replace("```json", "").replace("```", "").strip()
            analysis = json.loads(raw)

            job["score"]         = analysis.get("score", 0)
            job["resume"]        = analysis.get("resume", "")
            job["points_forts"]  = analysis.get("points_forts", [])
            job["points_faibles"]= analysis.get("points_faibles", [])
            job["verdict"]       = analysis.get("verdict", "")

        except json.JSONDecodeError as e:
            print(f"    ⚠️  Erreur de parsing JSON : {e}")
            job["score"]   = 0
            job["verdict"] = "Erreur d'analyse"

        except Exception as e:
            print(f"    ⚠️  Erreur API : {e}")
            job["score"]   = 0
            job["verdict"] = str(e)

        scored.append(job)

        # Petite pause pour respecter les rate limits
        if i % 10 == 0:
            time.sleep(2)

    # Trier par score décroissant et filtrer
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    filtered = [j for j in scored if j.get("score", 0) >= MIN_SCORE]

    print(f"\n✅ {len(filtered)} offres retenues (score ≥ {MIN_SCORE}/10)")
    return filtered
