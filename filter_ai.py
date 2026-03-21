import json
import re
import time
from groq import Groq
from config import GROQ_API_KEY
import sqlite3

DB_PATH = "aphp_jobs.db"

# Mots-clés qui garantissent un passage automatique SANS appel LLM
PASS_KEYWORDS = [
    "master", "bac+5", "bac + 5", "diplôme d'ingénieur", "diplome d'ingenieur",
    "école d'ingénieur", "ecole d'ingenieur", "ingénieur ou", "ingénieur et",
    "grande école", "grande ecole", "école de commerce", "ecole de commerce",
    "msc", "mba", "doctorat", "phd", "ph.d", "bac +5",
    "niveau master", "niveau ingénieur", "formation bac+5",
    "diplôme de niveau", "niveau 7", "niveau i", "niveau ii",
]

PASS_METIERS = [
    "Ingénieur - Etudes- Données en recherche clinique",
    "Expertise SI - Réseaux télécom & système - Infrastructure - Data",
    "Applications - Développement",
    "Chefferie de Projet - MOA",
    "Finance - Contrôle de gestion",
    "Gestion médico- administrative, traitement - analyse de l'information médicale",
]

def load_unfiltered_jobs() -> list[dict]:
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
    conn.execute("UPDATE jobs SET rejection_category = ?, rejection_reason = ? WHERE id = ?",
                 (category, reason, job_id))
    conn.commit()
    conn.close()

def mark_passed(job_id: str, reason: str = "Passe le filtre IA étape 1"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET rejection_category = 'passed_filter_1', rejection_reason = ? WHERE id = ?",
                 (reason, job_id))
    conn.commit()
    conn.close()

def check_pass_keywords(job: dict) -> str | None:
    """Retourne le mot-clé trouvé si l'offre mentionne Bac+5, sinon None."""
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    for kw in PASS_KEYWORDS:
        if kw in text:
            return kw
    return None

PROMPT_TEMPLATE = """
Tu es un assistant de recrutement. Analyse cette offre selon les règles suivantes.

## OFFRE
Titre   : {title}
Métier  : {metier}
Filière : {filiere}
Description : {description}

## RÈGLES (dans cet ordre strict)

### RÈGLE 1 — REJET DIPLÔME PARAMÉDICAL
Si l'offre exige un diplôme paramédical ou médical comme condition obligatoire :
diplôme d'État infirmier, DEI, IBODE, IADE, sage-femme, aide-soignant,
auxiliaire de puériculture, DTS manipulateur, électroradiologie...
→ résultat = "reject", categorie = "diplome_paramedical"

IMPORTANT : Le fait qu'un poste soit dans un hôpital ou un service technique
hospitalier NE signifie PAS que c'est un poste paramédical. Un électricien,
plombier, technicien de maintenance dans un hôpital = surqualification (Règle 2),
pas diplôme paramédical.

### RÈGLE 2 — REJET SURQUALIFICATION
Rejeter si le poste est clairement non-cadre et sans dimension analytique/management,
ET que le niveau de diplôme requis est inférieur à Bac+5.

Exemples à rejeter :
- Poste technique opérationnel : électricien, plombier, magasinier, agent logistique,
  technicien de maintenance, cuisinier, agent de restauration, brancardier
- Poste administratif pur : secrétaire, standardiste, agent d'accueil, agent de facturation
- Diplôme requis : CAP, BEP, Bac, Bac pro, BTS, DUT, Bac+2

Ne PAS rejeter :
- Responsable, chef de projet, coordinateur, manager, directeur adjoint
- Ingénieur, analyste, data, statisticien, chargé de mission
- Tout poste avec dimension analytique, pilotage ou management d'équipe
- Si le niveau de diplôme n'est pas précisé → laisser passer

### RÈGLE 3 — PASSAGE PAR DÉFAUT
Dans tous les autres cas, laisser passer.
→ résultat = "pass"

## FORMAT DE RÉPONSE
Réponds UNIQUEMENT en JSON valide, sans Markdown :
{{
  "resultat": "pass" | "reject",
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

    passed = rejected = errors = auto_passed = 0

    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job['title'][:60]}...")

        if job.get("metier", "") in PASS_METIERS:
            mark_passed(job["id"], f"Passage automatique : métier qualifiant '{job.get('metier')}'")
            auto_passed += 1
            print(f"    ✅ Auto-pass métier : '{job.get('metier')}'")
            continue

        # ── Pré-check mots-clés Bac+5 → passage automatique sans LLM ──
        kw_found = check_pass_keywords(job)
        if kw_found:
            mark_passed(job["id"], f"Passage automatique : mot-clé '{kw_found}' détecté")
            auto_passed += 1
            print(f"    ✅ Auto-pass : '{kw_found}'")
            continue

        # ── Appel LLM pour les autres ────────────────────────────────
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

                if result["resultat"] == "reject":
                    mark_rejected(job["id"], result.get("categorie", "surqualification"), result["raison"])
                    rejected += 1
                else:
                    mark_passed(job["id"], result.get("raison", "Passe le filtre IA"))
                    passed += 1

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
                        print(f"    💾 {passed + auto_passed} passées, {rejected} rejetées jusqu'ici")
                        return
                    else:
                        print(f"    ⏳ Rate limit/minute, pause 60s...")
                        time.sleep(60)
                else:
                    break

        if not success:
            # En cas d'erreur → on laisse passer par sécurité
            mark_passed(job["id"], "Erreur analyse — passage par défaut")
            errors += 1

    print(f"\n✅ Filtre IA étape 1 terminé :")
    print(f"   ✅ Auto-passées (mots-clés) : {auto_passed}")
    print(f"   ✅ Passées (LLM)            : {passed}")
    print(f"   ❌ Rejetées                 : {rejected}")
    print(f"   ⚠️  Erreurs (passées quand même) : {errors}")

if __name__ == "__main__":
    run_filter_1()