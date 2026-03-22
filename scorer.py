import json
import re
import time
from groq import Groq
from config import GROQ_API_KEY, PROFILE_FACTUEL, PROFILE_MOTIVATIONNEL
import sqlite3

DB_PATH = "aphp_jobs.db"

def load_jobs_to_score() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, description
        FROM jobs
        WHERE status = 'active'
        AND rejection_category = 'passed_filter_1'
        AND score IS NULL
    """).fetchall()
    conn.close()
    cols = ["id","title","metier","filiere","hopital","location",
            "contrat","teletravail","description"]
    return [dict(zip(cols, r)) for r in rows]

def load_feedbacks() -> list[dict]:
    """Charge les feedbacks pour enrichir le prompt."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT f.decision, f.commentaire, j.title, j.metier, j.filiere
        FROM feedbacks f
        JOIN jobs j ON f.job_id = j.id
        ORDER BY f.created_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    return [{"decision": r[0], "commentaire": r[1],
             "title": r[2], "metier": r[3], "filiere": r[4]} for r in rows]

def build_feedback_examples(feedbacks: list[dict]) -> str:
    """Formate les feedbacks comme exemples few-shot."""
    if not feedbacks:
        return "Aucun feedback disponible pour l'instant."

    lines = []
    for f in feedbacks:
        decision_label = {
            "⭐": "EXCELLENT",
            "👍": "INTÉRESSANT",
            "👎": "PAS INTÉRESSANT"
        }.get(f["decision"], f["decision"])

        line = f"- {decision_label} : '{f['title']}' ({f['metier']})"
        if f["commentaire"]:
            line += f" → \"{f['commentaire']}\""
        lines.append(line)

    return "\n".join(lines)

def save_score(job_id: str, score: int, priorite: str,
               raison: str, points_forts: list, points_faibles: list):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs
        SET score = ?, priorite = ?, score_raison = ?,
            score_points_forts = ?, score_points_faibles = ?
        WHERE id = ?
    """, (
        score, priorite, raison,
        json.dumps(points_forts, ensure_ascii=False),
        json.dumps(points_faibles, ensure_ascii=False),
        job_id
    ))
    conn.commit()
    conn.close()

PROMPT_TEMPLATE = """
Tu es un recruteur senior à l'AP-HP. Tu reçois le CV d'un candidat et une offre d'emploi.
Ton rôle est d'évaluer honnêtement si ce candidat serait retenu ou écarté pour ce poste.
Tu dois être critique et identifier les vrais points de friction, pas juste les similitudes.

## PROFIL FACTUEL DU CANDIDAT
{profile_factuel}

## CE QUE RECHERCHE LE CANDIDAT
{profile_motivationnel}

## CE QUE LE CANDIDAT A APPRÉCIÉ / PAS APPRÉCIÉ SUR D'AUTRES OFFRES
{feedback_examples}

## OFFRE À ÉVALUER
Titre        : {title}
Métier       : {metier}
Filière      : {filiere}
Hôpital      : {hopital}
Localisation : {location}
Contrat      : {contrat}
Télétravail  : {teletravail}
Description  : {description}

## INSTRUCTIONS

En tant que recruteur, évalue :

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
   - P1 (score ≥ 80) : excellent match des deux côtés, peu de friction
   - P2 (score 60-79) : bon potentiel mais points à vérifier en entretien
   - P3 (score 40-59) : match partiel, risque réel de rejet ou de déception
   - En dessous de 40 : ne pas recommander

Réponds UNIQUEMENT en JSON valide, sans Markdown, sans texte avant ou après :
{{
  "score": <0-100>,
  "priorite": "P1" | "P2" | "P3",
  "raison": "<2-3 phrases honnêtes depuis le point de vue recruteur>",
  "points_forts": ["<point 1>", "<point 2>"],
  "points_faibles": ["<point éliminatoire potentiel 1>", "<point 2>"]
}}
"""

def run_scorer(limit: int = None):
    if not GROQ_API_KEY:
        raise ValueError("❌ GROQ_API_KEY manquante !")

    client = Groq(api_key=GROQ_API_KEY)
    jobs = load_jobs_to_score()
    feedbacks = load_feedbacks()
    feedback_examples = build_feedback_examples(feedbacks)

    if limit:
        jobs = jobs[:limit]

    print(f"\n🎯 Scoring profil — {len(jobs)} offres à évaluer...")
    if feedbacks:
        print(f"   📚 {len(feedbacks)} feedbacks injectés dans le prompt")
    else:
        print(f"   📚 Aucun feedback encore — le scoring sera basé sur le profil seul")

    scored = errors = 0

    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job['title'][:60]}...")

        prompt = PROMPT_TEMPLATE.format(
            profile_factuel=PROFILE_FACTUEL,
            profile_motivationnel=PROFILE_MOTIVATIONNEL,
            feedback_examples=feedback_examples,
            title=job.get("title", ""),
            metier=job.get("metier", ""),
            filiere=job.get("filiere", ""),
            hopital=job.get("hopital", ""),
            location=job.get("location", ""),
            contrat=job.get("contrat", ""),
            teletravail=job.get("teletravail", ""),
            description=job.get("description", "")[:2000],
        )

        success = False
        for attempt in range(5):
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                )
                raw = response.choices[0].message.content.strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if not match:
                    raise ValueError(f"Pas de JSON : {raw[:80]}")
                result = json.loads(match.group(0))

                score    = int(result.get("score", 0))
                priorite = result.get("priorite", "P3")
                raison   = result.get("raison", "").strip()
                pf       = result.get("points_forts", [])
                pp       = result.get("points_faibles", [])

                if not raison:
                    raison = "Pas de justification fournie"

                save_score(job["id"], score, priorite, raison, pf, pp)
                scored += 1
                print(f"    🎯 {priorite} — {score}/100 : {raison[:80]}")

                save_score(job["id"], score, priorite, raison, pf, pp)
                scored += 1
                print(f"    🎯 {priorite} - {score}/100 : {raison[:80]}")

                # Rejeter automatiquement les offres avec score < 50
                if score < 50:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("""
                        UPDATE jobs SET rejection_category = 'profil_inadequat',
                        rejection_reason = ?
                        WHERE id = ?
                    """, (f"Score trop bas ({score}/100) : {raison}", job["id"]))
                    conn.commit()
                    conn.close()
                    print(f"    ❌ Rejeté automatiquement (score < 50)")


                success = True
                break

            except Exception as e:
                err = str(e)
                print(f"    ⚠️  Erreur : {err}")
                if "429" in err or "rate_limit" in err:
                    if "per day" in err or "TPD" in err:
                        match_wait = re.search(r'try again in (.+?)\.', err)
                        wait_msg = f"Réessaie dans : {match_wait.group(1)}" if match_wait else ""
                        print(f"    🛑 Limite journalière ! {wait_msg}")
                        print(f"    💾 {scored} offres scorées jusqu'ici")
                        return
                    else:
                        print(f"    ⏳ Rate limit/minute, pause 60s...")
                        time.sleep(60)
                else:
                    break

        if not success:
            errors += 1

    print(f"\n✅ Scoring terminé :")
    print(f"   🎯 Scorées  : {scored}")
    print(f"   ⚠️  Erreurs : {errors}")

if __name__ == "__main__":
    run_scorer()