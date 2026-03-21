import json
import time
from groq import Groq
from config import GROQ_API_KEY
import sqlite3
import re

DB_PATH = "aphp_jobs.db"

def load_unfiltered_jobs() -> list[dict]:
    """Charge les offres actives qui n'ont pas encore de rejet."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, title, metier, filiere, description
        FROM jobs
        WHERE status = 'active'
        AND rejection_category IS NULL
    """).fetchall()
    conn.close()
    cols = ["id", "title", "metier", "filiere", "description"]
    return [dict(zip(cols, r)) for r in rows]

def mark_rejected(job_id: str, category: str, reason: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs SET rejection_category = ?, rejection_reason = ?
        WHERE id = ?
    """, (category, reason, job_id))
    conn.commit()
    conn.close()

def mark_passed(job_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE jobs SET rejection_category = 'passed_filter_1', rejection_reason = 'Passe le filtre IA étape 1'
        WHERE id = ?
    """, (job_id,))
    conn.commit()
    conn.close()

PROMPT_TEMPLATE = """
Tu es un assistant de recrutement. Analyse cette offre d'emploi et classe-la selon 3 règles strictes.

## OFFRE
Titre   : {title}
Métier  : {metier}
Filière : {filiere}
Description : {description}

## RÈGLES (appliquées dans cet ordre)

### RÈGLE 1 — PASSAGE AUTOMATIQUE (priorité absolue)
Si l'offre mentionne explicitement une formation Bac+5, peu importe comment c'est formulé :
diplôme d'ingénieur, école d'ingénieur, école d'ingénieurs, ingénieur, master, bac+5,
formation supérieure, école de commerce, grande école, MBA, MSc, formation bac +5...
→ résultat = "pass", raison = "Formation Bac+5 mentionnée : [cite le texte exact]"

### RÈGLE 2 — REJET DIPLÔME PARAMÉDICAL
Si l'offre exige un diplôme paramédical ou médical :
diplôme d'État infirmier, DEI, diplôme infirmier, cadre de santé, DTS manipulateur,
électroradiologie, IBODE, IADE, sage-femme, aide-soignant, auxiliaire de puériculture...
→ résultat = "reject", categorie = "diplome_paramedical", raison = "Diplôme paramédical requis : [cite le texte exact]"

### RÈGLE 3 — REJET SURQUALIFICATION
Si l'offre est clairement un poste non-cadre sans dimension analytique/management :
nettoyage, entretien, agent de service, brancardier, secrétariat pur, facturation,
standard, accueil seul, cuisine, restauration, logistique opérationnelle...
→ résultat = "reject", categorie = "surqualification", raison = "Poste non-cadre : [décris le poste en 5 mots]"

### RÈGLE 4 — INCERTAIN
Si aucune règle ne s'applique clairement.
→ résultat = "uncertain"

## FORMAT DE RÉPONSE
Réponds UNIQUEMENT en JSON valide, sans Markdown :
{{
  "resultat": "pass" | "reject" | "uncertain",
  "categorie": "diplome_paramedical" | "surqualification" | null,
  "raison": "<explication courte>"
}}
"""

def run_filter_1(limit: int = None):
    if not GROQ_API_KEY:
        raise ValueError("❌ GROQ_API_KEY manquante !")

    client = Groq(api_key=GROQ_API_KEY)
    jobs = load_unfiltered_jobs()

    if limit:
        jobs = jobs[:limit]

    print(f"\n🤖 Filtre IA étape 1 — {len(jobs)} offres à analyser...")

    passed = rejected = uncertain = errors = 0

    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job['title'][:60]}...")

        prompt = PROMPT_TEMPLATE.format(
            title=job.get("title", ""),
            metier=job.get("metier", ""),
            filiere=job.get("filiere", ""),
            description=job.get("description", "")[:1500],
        )

        success = False
        for attempt in range(5):
            try:
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                )
                raw = response.choices[0].message.content.strip()
                match = re.search(r'\{.*?\}', raw, re.DOTALL)
                if not match:
                    raise ValueError(f"Pas de JSON : {raw[:80]}")
                result = json.loads(match.group(0))

                if result["resultat"] == "pass":
                    mark_passed(job["id"])
                    passed += 1
                elif result["resultat"] == "reject":
                    mark_rejected(job["id"], result.get("categorie", "surqualification"), result["raison"])
                    rejected += 1
                else:
                    # uncertain → on laisse passer par défaut
                    mark_passed(job["id"])
                    uncertain += 1

                success = True
                break

            except Exception as e:
                err = str(e)
                print(f"    ⚠️  Erreur : {err}")
                if "429" in err or "rate_limit" in err:
                    if "per day" in err or "TPD" in err:
                        match = re.search(r'try again in (.+?)\.', err)
                        wait_msg = f"Réessaie dans : {match.group(1)}" if match else ""
                        print(f"    🛑 Limite journalière ! {wait_msg}")
                        print(f"    💾 {passed} passées, {rejected} rejetées, {uncertain} incertaines jusqu'ici")
                        return
                    else:
                        print(f"    ⏳ Rate limit/minute, pause 60s...")
                        time.sleep(60)
                else:
                    break

        if not success:
            errors += 1

    print(f"\n✅ Filtre IA étape 1 terminé :")
    print(f"   ✅ Passées    : {passed}")
    print(f"   ❌ Rejetées   : {rejected}")
    print(f"   ❓ Incertaines : {uncertain}")
    print(f"   ⚠️  Erreurs    : {errors}")


if __name__ == "__main__":
    run_filter_1(limit=50)