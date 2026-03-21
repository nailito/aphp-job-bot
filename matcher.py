import json
import time
from groq import Groq
from config import GROQ_API_KEY, PROFILE, MIN_SCORE, EXCLUDED_TITLE_KEYWORDS, ACCEPTED_LOCATIONS

def pre_filter(jobs):
    filtered, excluded = [], 0
    for job in jobs:
        title_lower = job.get("title", "").lower()
        if any(kw in title_lower for kw in EXCLUDED_TITLE_KEYWORDS):
            excluded += 1
            continue
        if ACCEPTED_LOCATIONS and not any(loc in job.get("location", "") for loc in ACCEPTED_LOCATIONS):
            excluded += 1
            continue
        filtered.append(job)
    print(f"  🚫 Pré-filtre : {excluded} exclues, {len(filtered)} restantes pour le LLM")
    return filtered


def score_jobs(jobs):
    if not GROQ_API_KEY:
        raise ValueError("❌ GROQ_API_KEY manquante !")

    client = Groq(api_key=GROQ_API_KEY)
    jobs = pre_filter(jobs)
    scored = []
    print(f"\n🤖 Scoring LLM de {len(jobs)} offres (~{len(jobs)*3//60} min estimées)...")

    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job.get('title', '')[:60]}...")

        prompt = f"""
Tu es un assistant expert en recrutement. Analyse l'adéquation entre ce profil et cette offre.

{PROFILE}

---

## OFFRE À ANALYSER
Titre        : {job.get('title', '')}
Métier       : {job.get('metier', '')}
Filière      : {job.get('filiere', '')}
Hôpital      : {job.get('hopital', '')}
Localisation : {job.get('location', '')}
Contrat      : {job.get('contrat', '')}
Télétravail  : {job.get('teletravail', '')}
Description  : {job.get('description', '')[:2000]}

---

Réponds UNIQUEMENT en JSON valide, sans Markdown :
{{
  "score": <entier 0 à 100>,
  "mots_cles_matches": ["mot1", "mot2"],
  "raison": "<2-3 phrases>",
  "points_forts": ["point1", "point2"],
  "points_faibles": ["point1"]
}}
"""

        success = False
        for attempt in range(5):
            try:
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                )
                raw = response.choices[0].message.content.strip()
                raw = raw.replace("```json", "").replace("```", "").strip()
                analysis = json.loads(raw)

                job["score"]             = analysis.get("score", 0)
                job["mots_cles_matches"] = ", ".join(analysis.get("mots_cles_matches", []))
                job["raison"]            = analysis.get("raison", "")
                job["points_forts"]      = analysis.get("points_forts", [])
                job["points_faibles"]    = analysis.get("points_faibles", [])
                success = True
                break

            except Exception as e:
                print(f"    ⚠️  Erreur : {e}")
                if "429" in str(e) or "rate_limit" in str(e):
                    if "per day" in str(e) or "TPD" in str(e):
                        import re
                        match = re.search(r'try again in (.+?)\.', str(e))
                        wait_msg = f"Réessaie dans : {match.group(1)}" if match else ""
                        print(f"    🛑 Limite journalière atteinte ! {wait_msg}")
                        print(f"    💾 Sauvegarde des {len(scored)} offres déjà scorées...")
                        break
                    else:
                        print(f"    ⏳ Rate limit/minute, pause 60s...")
                        time.sleep(60)
                else:
                    import traceback
                    traceback.print_exc()
                    break

        if not success:
            job["score"]             = 0
            job["raison"]            = "Erreur scoring"
            job["mots_cles_matches"] = ""
            job["points_forts"]      = []
            job["points_faibles"]    = []

        scored.append(job)
        time.sleep(3)  # 20 req/min → sous la limite de 30

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    result = [j for j in scored if j.get("score", 0) >= MIN_SCORE]
    print(f"\n✅ {len(result)} offres retenues (score ≥ {MIN_SCORE}/100)")
    return result