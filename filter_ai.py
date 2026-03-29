import json
import re
import time
import os
import psycopg2
from groq import Groq
from config import GROQ_API_KEY
from tqdm import tqdm
from datetime import datetime, timezone, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ─────────────────────────
# TELEGRAM (AJOUT UNIQUEMENT)
# ─────────────────────────
def notify(msg):
    print(msg)
    try:
        from notifier import send_telegram
        send_telegram(msg)
    except Exception as e:
        print(f"(Telegram failed: {e})")
# ─────────────────────────

PASS_KEYWORDS = [
    "bac+5", "bac + 5", "diplôme d'ingénieur", "diplome d'ingenieur",
    "école d'ingénieur", "ecole d'ingenieur", "ingénieur ou", "ingénieur et",
    "grande école", "grande ecole", "école de commerce", "ecole de commerce",
    "msc", "doctorat", "phd", "ph.d", "bac +5",
    "niveau ingénieur", "formation bac+5",
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

REJECT_TITLE_KEYWORDS = [
    "magasinier", "électricien", "plombier", "cuisinier",
    "agent de restauration", "brancardier", "agent de stérilisation",
    "agent logistique", "agent de service", "standardiste",
    "agent d'accueil", "agent de facturation", "gestionnaire de stocks",
    "agent d'entretien", "lingère", "chauffeur", "ambulancier",
    "technicien polyvalent", "technicien de maintenance",
    "technicien biomédical", "technicien de laboratoire",
    "technicien en recherche", "technicien d'information médicale",
    "enseignant en activités physiques",
]

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def load_unfiltered_jobs() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, metier, filiere, description
                FROM jobs
                WHERE status = 'active'
                AND (rejection_category IS NULL OR rejection_category = 'a_trier')
            """)
            rows = cur.fetchall()
    cols = ["id", "title", "metier", "filiere", "description"]
    return [dict(zip(cols, r)) for r in rows]


def is_too_old(job: dict, max_days: int = 90) -> bool:
    raw = job.get("date_publication")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days > max_days
    except Exception:
        return False



def mark_rejected(job_id: str, category: str, reason: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs SET rejection_category = %s, rejection_reason = %s
                WHERE id = %s
            """, (category, reason, job_id))
        conn.commit()

def mark_passed(job_id: str, reason: str = "Passe le filtre IA étape 1"):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs SET rejection_category = 'passed_filter_1', rejection_reason = %s
                WHERE id = %s
            """, (reason, job_id))
        conn.commit()

def check_pass_keywords(job: dict) -> str | None:
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    for kw in PASS_KEYWORDS:
        if kw in text:
            return kw
    return None

PROMPT_TEMPLATE = """Tu es un assistant de recrutement. Analyse cette offre selon les règles suivantes.

## OFFRE
Titre   : {title}
Métier  : {metier}
Filière : {filiere}
Description : {description}

## RÈGLES (dans cet ordre strict)

### RÈGLE 1 — REJET DIPLÔME PARAMÉDICAL
Si l'offre exige un diplôme paramédical ou médical comme condition obligatoire :
diplôme d'État infirmier, DEI, IBODE, IADE, sage-femme, aide-soignant, cadre de santé,
auxiliaire de puériculture, DTS manipulateur, électroradiologie...
→ résultat = "reject", categorie = "diplome_paramedical"

IMPORTANT : Le fait qu'un poste soit dans un hôpital ou un service technique
hospitalier NE signifie PAS que c'est un poste paramédical. Un électricien,
plombier, technicien de maintenance dans un hôpital = surqualification (Règle 2),
pas diplôme paramédical.

### RÈGLE 2 — REJET : POSTE TROP BAS NIVEAU POUR UN BAC+5
Rejeter si le poste est clairement destiné à un niveau CAP/BEP/Bac/Bac+2 :
- Poste technique opérationnel sans encadrement : électricien, plombier,
  magasinier, agent logistique, technicien de maintenance, cuisinier,
  agent de restauration, brancardier, agent de stérilisation
- Poste administratif d'exécution : secrétaire, standardiste, agent d'accueil,
  agent de facturation, gestionnaire de stocks
- Le niveau de diplôme requis est CAP, BEP, Bac, Bac pro, BTS, DUT, Bac+2, Bac+3

→ résultat = "reject", categorie = "surqualification",
  raison = "Candidat surqualifié : poste de niveau [CAP/Bac/Bac+2] pour un ingénieur Bac+5"

### RÈGLE 3 — WHITELIST : POSTE TYPIQUEMENT OCCUPÉ PAR UN BAC+5
Si les règles 1 et 2 ne s'appliquent pas, vérifie si le poste est typiquement
occupé par quelqu'un issu d'une école d'ingénieur ou de commerce Bac+5 (master, doctorat).

→ "pass" si le poste correspond à l'un de ces profils :
✅ Ingénieur (toute spécialité : biomédical, méthodes, qualité, SI, data...)
✅ Cadre administratif, chargé de mission, chef de projet
✅ Contrôleur de gestion, analyste financier, acheteur senior
✅ Data analyst, statisticien, chercheur, biostatisticien
✅ Consultant, manager, directeur adjoint, responsable de service
✅ Tout poste où une grande école ou un master est la norme du secteur

→ "reject" si le poste est typiquement occupé par un Bac, BTS ou DUT :
technicien, opérateur, agent, magasinier, électricien, cuisinier...
→ "reject" si le poste est pour un profil en droit, en enseignement ou en ressources humaines

En cas de doute → "pass"

## FORMAT DE RÉPONSE
Tu dois répondre UNIQUEMENT avec le JSON, sans aucun texte avant ou après.
Pas d'introduction, pas d'explication, pas de conclusion.
Commence directement par {{ et termine par }}.
{{
  "resultat": "pass" | "reject",
  "categorie": "diplome_paramedical" | "surqualification" | null,
  "raison": "<obligatoire : explique en 1 phrase pourquoi pass ou reject>"
}}
"""

def run_filter_1(limit: int = None):
    if not GROQ_API_KEY:
        raise ValueError("❌ GROQ_API_KEY manquante !")

    client = Groq(api_key=GROQ_API_KEY)
    jobs = load_unfiltered_jobs()

    if limit:
        jobs = jobs[:limit]

    total = len(jobs)
    print(f"\n🤖 Filtre IA étape 1 — {total} offres à analyser...")

    # ─────────────────────────
    # TELEGRAM START (AJOUT)
    # ─────────────────────────
    notify(f"""🚫 Étape 2 — Filtre IA en cours...

📊 {total} offres à analyser
""")
    start_time = time.time()
    # ─────────────────────────

    passed = rejected = errors = auto_passed = 0

    for i, job in enumerate(tqdm(jobs, desc="Filtre IA"), 1):
        print(f"  [{i}/{total}] {job['title'][:60]}...")

        if job.get("metier", "") in PASS_METIERS:
            mark_passed(job["id"], f"Passage automatique : métier qualifiant '{job.get('metier')}'")
            auto_passed += 1
            print(f"    🙈 Auto-pass métier : '{job.get('metier')}'")
            continue

        if is_too_old(job):
            mark_rejected(job["id"], "trop_ancienne",
                          f"Offre publiée il y a plus de 90 jours ({job.get('date_publication', '')[:10]})")
            rejected += 1
            print(f"    📅 Rejetée (trop ancienne) : {job.get('date_publication', '')[:10]}")
            continue

        kw_found = check_pass_keywords(job)
        if kw_found:
            mark_passed(job["id"], f"Passage automatique : mot-clé '{kw_found}' détecté")
            auto_passed += 1
            print(f"    🙈 Auto-pass bac+5 : '{kw_found}'")
            continue

        title_lower = job.get("title", "").lower()
        kw_reject = next((kw for kw in REJECT_TITLE_KEYWORDS if kw in title_lower), None)
        if kw_reject:
            mark_rejected(job["id"], "surqualification",
                          f"Candidat surqualifié (Bac+5) pour ce poste : '{kw_reject}' détecté dans le titre")
            rejected += 1
            print(f"    ❌ Auto-reject titre : '{kw_reject}'")
            continue

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
                    model="moonshotai/kimi-k2-instruct",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                )
                raw = response.choices[0].message.content.strip()
                match = re.search(r'\{[^{}]*"resultat"[^{}]*\}', raw, re.DOTALL)
                if not match:
                    match = re.search(r'\{.*\}', raw, re.DOTALL)
                if not match:
                    raise ValueError(f"Pas de JSON : {raw[:80]}")
                result = json.loads(match.group(0))

                raison = result.get("raison", "").strip()
                if not raison:
                    raison = f"Pas de raison fournie — résultat brut : {result.get('resultat')}"

                if result["resultat"] == "reject":
                    mark_rejected(job["id"], result.get("categorie", "surqualification"), raison)
                    rejected += 1
                    print(f"    ❌ Rejeté ({result.get('categorie','?')}) : {raison}")
                else:
                    mark_passed(job["id"], raison)
                    passed += 1
                    print(f"    ✅ Accepté : {raison}")

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
                        remaining = jobs[i:]
                        with get_connection() as conn:
                            with conn.cursor() as cur:
                                for remaining_job in remaining:
                                    cur.execute("""
                                        UPDATE jobs SET rejection_category = 'a_trier'
                                        WHERE id = %s
                                    """, (remaining_job["id"],))
                            conn.commit()
                        print(f"    💾 {len(remaining)} offres marquées 'à trier'")
                        print(f"    💾 {passed + auto_passed} passées, {rejected} rejetées jusqu'ici")
                        return
                    else:
                        print(f"    ⏳ Rate limit/minute, pause 60s...")
                        time.sleep(60)
                else:
                    break

        if not success:
            mark_passed(job["id"], "Erreur analyse — passage par défaut")
            errors += 1

    print("\n📊 Résumé Filtre IA :")
    print(f"   → {total} analysées")
    print(f"   → {auto_passed} auto-pass")
    print(f"   → {passed} acceptées (LLM)")
    print(f"   → {rejected} rejetées")
    print(f"   → {errors} erreurs")

    print(f"\n✅ Filtre IA étape 1 terminé :")
    print(f"   🙈 Auto-passées  : {auto_passed}")
    print(f"   ✅ Passées (LLM) : {passed}")
    print(f"   ❌ Rejetées      : {rejected}")
    print(f"   ⚠️  Erreurs       : {errors}")

    # ─────────────────────────
    # TELEGRAM END (AJOUT)
    # ─────────────────────────
    elapsed = int(time.time() - start_time)
    kept = passed + auto_passed
    ratio = (kept / total * 100) if total else 0

    notify(f"""🚫 Filtrage APHP terminé

📊 {total} → {kept} offres ({ratio:.1f}%)
❌ {rejected} rejetées
⚠️ {errors} erreurs

⏱️ {elapsed}s
""")
    # ─────────────────────────

if __name__ == "__main__":
    run_filter_1()