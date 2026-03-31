"""
filter_hcl.py
"""

import logging
from tqdm import tqdm
from database_hcl import get_offers_to_filter, update_ai_filter
logger = logging.getLogger(__name__)
import json
import re
import time
import os
from datetime import datetime, timedelta, date
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

PROMPT_TEMPLATE = """Tu es un assistant de recrutement. Tu analyses des offres d'emploi des Hospices Civils de Lyon (HCL) pour le compte d'un candidat ingénieur.

## PROFIL DU CANDIDAT
Ingénieur diplômé de l'École Centrale de Lyon (Bac+5, diplôme d'ingénieur généraliste).
Compétences : gestion de projet, data, systèmes d'information, qualité, biomédical, contrôle de gestion, achat, management.
Recherche : tout poste à responsabilité dans un environnement hospitalier pouvant être occupé par un ingénieur ou un cadre Bac+5.
N'est PAS intéressé par : les postes purement techniques d'exécution (électricien, plombier...), les postes paramédicaux, les postes de niveau Bac/BTS.

## OFFRE
Titre       : {titre}
Filière HCL : {filiere}
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
Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
{{
  "resultat": "pass" | "reject",
  "categorie": "diplome_paramedical" | "surqualification" | null,
  "raison": "<1 phrase obligatoire>"
}}
"""


def _ai_filter(job: dict, client: Groq) -> tuple[str, str | None, str]:
    prompt = PROMPT_TEMPLATE.format(
        titre=job.get("titre", ""),
        filiere=job.get("filiere", ""),
        description=(job.get("description") or "")[:1500],
    )

    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model="moonshotai/kimi-k2-instruct",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            raw = response.choices[0].message.content.strip()

            match = re.search(r'\{[^{}]*"resultat"[^{}]*\}', raw, re.DOTALL)
            if not match:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                raise ValueError(f"Pas de JSON trouvé : {raw[:80]}")

            result = json.loads(match.group(0))
            raison = result.get("raison", "").strip() or "Pas de raison fournie"
            decision = result.get("resultat", "pass")
            categorie = result.get("categorie")

            return decision, categorie, raison

        except Exception as e:
            err_str = str(e)
            logger.warning(f"    Tentative {attempt+1}/4 échouée : {err_str[:80]}")

            if "429" in err_str or "rate_limit" in err_str:
                if "per day" in err_str or "TPD" in err_str:
                    raise RuntimeError(f"Limite journalière Groq atteinte : {err_str}") from e
                wait = 60 if attempt < 2 else 120
                logger.info(f"    Rate limit minute — pause {wait}s")
                time.sleep(wait)
            else:
                break

    return "error", None, "Erreur LLM — passage par défaut"


PASS_KEYWORDS = [
    "bac+5", "bac + 5", "bac +5",
    "diplôme d'ingénieur", "diplome d'ingenieur",
    "école d'ingénieur", "ecole d'ingenieur",
    "grande école", "grande ecole",
    "école de commerce", "ecole de commerce",
    "master", "msc", "doctorat", "phd", "ph.d",
    "niveau 7", "niveau ii",
    "formation bac+5", "niveau ingénieur",
]

REJECT_TITLE_KEYWORDS = [
    # Métiers du bâtiment / maintenance
    "électricien", "plombier", "menuisier", "peintre", "soudeur",
    "chauffagiste", "climaticien", "maçon", "serrurier",
    "technicien de maintenance", "technicien polyvalent",
    "technicien biomédical",
    # Logistique / transport
    "chauffeur", "ambulancier", "manutentionnaire", "magasinier",
    "agent logistique", "agent de logistique",
    "livreur", "coursier",
    # Restauration / hôtellerie
    "cuisinier", "cuisinière", "aide-cuisinier",
    "agent de restauration", "agent restauration",
    "plongeur",
    # Nettoyage / entretien
    "agent de service", "agent d'entretien", "agent de nettoyage",
    "agent de propreté", "technicien de surface", "ouvrier d'entretien",
    # Santé / soins de base
    "brancardier", "agent de stérilisation",
    "lingère", "aide-soignant",
    # Sécurité
    "agent de sécurité", "agent de surveillance",
    # Administratif d'exécution
    "standardiste", "agent d'accueil", "hôte d'accueil",
    "agent de facturation", "gestionnaire de stocks",
    "secrétaire médical", "secrétaire médicale",
    # Profils hors ingénierie
    "juriste", "avocat", "enseignant", "professeur", "formateur",
    "ressources humaines", "rh", "recruteur", "chargé de recrutement",
    #medical
    "Médecin", "médecin", "pharmacien", "pharmacienne", "psychologue",
]

# Diplômes ou certifications paramédicaux stricts.
# NE PAS mettre de noms de métiers/filières ici (risque de faux positifs
# sur des offres d'ingénieur qui mentionnent ces métiers comme interlocuteurs).
REJECT_PARAMEDICAL_KEYWORDS = [
    "Diplôme Cadre de Santé",
    # Diplômes infirmiers
    "diplôme d'état infirmier", "diplome d'etat infirmier",
    "diplôme d'état d'infirmier", "diplome d'etat d'infirmier",
    "Diplôme Infirmier",
    "d.e. infirmier", "d.e infirmier",
    "ibode", "iade",
    # Diplômes aides-soignants / auxiliaires
    "diplôme d'état aide-soignant", "diplome d'etat aide-soignant",
    "diplôme d'état d'aide-soignant",
    "deas",  # Diplôme d'État d'Aide-Soignant
    "deap",  # Diplôme d'État d'Auxiliaire de Puériculture
    "auxiliaire de puériculture", "auxiliaire de puericulture",
    # Diplômes sage-femme / maïeutique
    "diplôme d'état de sage-femme", "diplome d'etat de sage-femme",
    # Diplômes de rééducation
    "diplôme d'état de masseur", "diplome d'etat de masseur",
    "diplôme d'état de kinésithérapeute",
    # Diplômes médico-technique / imagerie
    "diplôme d'état de manipulateur", "diplome d'etat de manipulateur",
    "dts manipulateur",
    "electroradiologie", "électroradiologie",
    # Cadre de santé
    "diplôme de cadre de santé", "diplome de cadre de sante",
    "Master 2 de Psychologie","DESS Psychologie","école de psychologues ",
    "D.E.S",
]

# Niveaux de diplôme explicitement trop bas pour un ingénieur Bac+5.
# Si une offre liste l'un de ces niveaux comme prérequis, elle n'est pas adaptée.
REJECT_DIPLOMA_LEVEL_KEYWORDS = [
    "bac+2", "bac +2", "bac + 2",
    "bac+3", "bac +3", "bac + 3",
    "dut", "bts",
    "bac pro", "bac pro assp", "bac pro sapat",
    "licence professionnelle",
]

REJECT_FILIERES = [
    "Infirmier",
    "Aide-soignant",
    "Sage-femme",
    "Rééducation",
    "Infirmier spécialisé",
    "Métiers du soin",
    "Secrétariat médical",
    "Pharmacie",
    "Médico-technique",
    "Socio-éducatif, psychologue",
    "Puériculture",
    "Orthophonie",
]

# Valeurs à rejeter dans le champ contrat (recherche partielle, insensible à la casse)
REJECT_CONTRATS = [
    "stage",
    "alternance",
]


def _text(job: dict, *fields: str) -> str:
    parts = [str(job.get(f) or "") for f in fields]
    return " ".join(parts).lower()


def _check_keywords(text: str, keywords: list[str]) -> str | None:
    for kw in keywords:
        if kw.lower() in text:
            return kw
    return None


def _auto_pass(job: dict) -> str | None:
    text = _text(job, "titre", "description")
    kw = _check_keywords(text, PASS_KEYWORDS)
    if kw:
        return f"Auto-pass : mot-clé Bac+5 détecté ('{kw}')"
    return None


def _reject_contrat(job: dict) -> tuple[str, str] | None:
    contrat = str(job.get("contrat") or "").strip().lower()
    if not contrat:
        return None
    for c in REJECT_CONTRATS:
        if c.lower() in contrat:
            return (
                "contrat_exclu",
                f"Auto-reject contrat : '{c}' détecté dans '{contrat}'",
            )
    return None


def _reject_filiere(job: dict) -> tuple[str, str] | None:
    filiere = str(job.get("filiere") or "").strip()
    if not filiere:
        return None
    for f in REJECT_FILIERES:
        if f.lower() in filiere.lower():
            return (
                "diplome_paramedical",
                f"Auto-reject filière : '{filiere}'",
            )
    return None


def _reject_paramedical(job: dict) -> tuple[str, str] | None:
    # Recherche dans titre + description — liste limitée aux diplômes stricts
    # pour éviter les faux positifs sur des offres d'ingénieur mentionnant
    # des métiers paramédicaux comme interlocuteurs.
    text = _text(job, "titre", "description")
    kw = _check_keywords(text, REJECT_PARAMEDICAL_KEYWORDS)
    if kw:
        return (
            "diplome_paramedical",
            f"Auto-reject paramédical : diplôme '{kw}' exigé",
        )
    return None


def _reject_diploma_level(job: dict) -> tuple[str, str] | None:
    # Si l'offre mentionne explicitement un niveau de diplôme trop bas,
    # elle n'est pas adaptée à un ingénieur Bac+5.
    text = _text(job, "titre", "description")
    kw = _check_keywords(text, REJECT_DIPLOMA_LEVEL_KEYWORDS)
    if kw:
        return (
            "surqualification",
            f"Auto-reject niveau diplôme : '{kw}' mentionné comme prérequis",
        )
    return None


def _reject_title(job: dict) -> tuple[str, str] | None:
    title = _text(job, "titre")
    kw = _check_keywords(title, REJECT_TITLE_KEYWORDS)
    if kw:
        return (
            "surqualification",
            f"Auto-reject titre : '{kw}' détecté",
        )
    return None


def run_filter(conn, limit: int = None) -> dict:
    groq_client = None
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY)
    else:
        logger.warning("GROQ_API_KEY absente — filtre IA désactivé, fallback pass pour tous")

    jobs = get_offers_to_filter(conn)
    if limit:
        jobs = jobs[:limit]
    total = len(jobs)

    stats = {
        "total": total,
        "auto_passed": 0,
        "fallback_passed": 0,
        "rejected": 0,
        "errors": 0,
        "ai_passed": 0,
        "ai_rejected": 0,
        "ai_errors": 0,
    }

    daily_limit_hit = False

    for job in tqdm(jobs, desc="Filtre HCL"):
        job_id = job["id"]
        titre = job.get("titre", "")[:60]

        try:
            # ── 0. Reject offre trop ancienne (> 6 mois)
            date_pub = job.get("date_publication")
            if date_pub:
                try:
                    age = date.today() - date.fromisoformat(str(date_pub)[:10])
                    if age.days > 183:
                        update_ai_filter(conn, job_id, "reject", "Auto-reject : offre de plus de 6 mois")
                        stats["rejected"] += 1
                        logger.debug(f"  ❌ Trop ancienne [{job_id}] {titre}")
                        continue
                except ValueError:
                    logger.warning(f"  ⚠️  date_publication invalide [{job_id}] : {date_pub}")

            # ── 1. Reject contrat (stage, alternance)
            result = _reject_contrat(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ Contrat [{job_id}] {titre} — {reason}")
                continue

            # ── 2. Reject titre
            result = _reject_title(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ Titre [{job_id}] {titre} — {reason}")
                continue

            # ── 3. Reject paramédical (diplômes stricts dans titre + description)
            result = _reject_paramedical(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ Paramédical [{job_id}] {titre} — {reason}")
                continue

            # ── 4. Reject niveau de diplôme trop bas (BTS, DUT, Bac+2, Bac+3...)
            result = _reject_diploma_level(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ Niveau diplôme [{job_id}] {titre} — {reason}")
                continue

            # ── 5. Reject filière
            result = _reject_filiere(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ Filière [{job_id}] {titre} — {reason}")
                continue

            # ── 6. Auto-pass Bac+5 (après tous les rejets)
            reason = _auto_pass(job)
            if reason:
                update_ai_filter(conn, job_id, "pass", reason)
                stats["auto_passed"] += 1
                logger.debug(f"  ✅ Auto-pass [{job_id}] {titre} — {reason}")
                continue

            # ── 7. Filtre IA
            if groq_client and not daily_limit_hit:
                try:
                    decision, categorie, raison = _ai_filter(job, groq_client)

                    if decision == "reject":
                        update_ai_filter(conn, job_id, "reject", raison)
                        stats["rejected"] += 1
                        stats["ai_rejected"] += 1
                        logger.debug(f"  ❌ IA [{job_id}] {titre} — {raison}")
                    elif decision == "error":
                        # Pas de mise à jour en base : le job sera retraité au prochain run
                        stats["ai_errors"] += 1
                        logger.warning(f"  ⚠️  IA error [{job_id}] {titre} — sera retraité")
                    else:
                        update_ai_filter(conn, job_id, "pass", raison)
                        stats["ai_passed"] += 1
                        logger.debug(f"  ✅ IA [{job_id}] {titre} — {raison}")

                except RuntimeError as e:
                    logger.error(f"Limite Groq TPD : {e}")
                    daily_limit_hit = True
                    logger.info(f"  ⏳ [{job_id}] laissé à trier (limite Groq journalière)")

            else:
                logger.debug(f"  ⏳ [{job_id}] laissé à trier (IA indisponible)")

        except Exception as e:
            logger.error(f"  ⚠️  Erreur sur job {job_id} : {e}")
            stats["errors"] += 1

    kept = stats["auto_passed"] + stats["fallback_passed"] + stats["ai_passed"]
    ratio = (kept / total * 100) if total else 0
    print(f"\n📊 Résumé filtre HCL :")
    print(f"   Total analysées      : {total}")
    print(f"   ✅ Auto-passées      : {stats['auto_passed']}")
    print(f"   🤖 IA passées        : {stats['ai_passed']}")
    print(f"   🟡 Fallback pass     : {stats['fallback_passed']}")
    print(f"   ❌ Rejetées          : {stats['rejected']}")
    print(f"   ⚠️  Erreurs IA        : {stats['ai_errors']}")
    print(f"   ⚠️  Erreurs générales : {stats['errors']}")
    print(f"   → Taux de rétention  : {ratio:.1f}%")

    return stats


if __name__ == "__main__":
    import os
    import psycopg as psycopg2
    from database_hcl import get_connection

    logging.basicConfig(level=logging.DEBUG)

    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = get_connection(DATABASE_URL)
    try:
        stats = run_filter(conn, limit=50)
    finally:
        conn.close()