"""
filter_hcl.py
Filtrage des offres HCL — étape 1.

Architecture :
  run_filter(conn) → dict de stats

Filtres appliqués dans cet ordre :
  1. Auto-pass  — mots-clés Bac+5 dans titre ou description
  2. Auto-reject — mots-clés de niveau insuffisant dans le titre
  3. Auto-reject — filières paramédicales / médicales dans le titre ou description
  [Slot IA — à implémenter plus tard]
  4. Fallback   — tout ce qui reste passe par défaut

Conventions database_hcl :
  - update_ai_filter(conn, job_id, decision, reason)
  - decision : 'pass' | 'reject'
"""

import logging
from tqdm import tqdm
from database_hcl import get_offers_to_filter, update_ai_filter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# LISTES DE FILTRES
# ─────────────────────────────────────────────

# Mots-clés qui signalent un poste Bac+5 → pass automatique
PASS_KEYWORDS = [
    "bac+5", "bac + 5", "bac +5",
    "diplôme d'ingénieur", "diplome d'ingenieur",
    "école d'ingénieur", "ecole d'ingenieur",
    "grande école", "grande ecole",
    "école de commerce", "ecole de commerce",
    "master", "msc", "doctorat", "phd", "ph.d",
    "niveau 7", "niveau i", "niveau ii",
    "formation bac+5", "niveau ingénieur",
]

# Mots-clés dans le TITRE qui signalent un poste trop bas niveau → reject
REJECT_TITLE_KEYWORDS = [
    # Technique opérationnel
    "électricien", "plombier", "cuisinier", "menuisier", "peintre",
    "chauffeur", "ambulancier", "manutentionnaire",
    "agent de restauration", "agent logistique", "agent de service",
    "agent d'entretien", "agent de stérilisation", "agent de sécurité",
    "brancardier", "lingère", "magasinier",
    "technicien de maintenance", "technicien polyvalent",
    "technicien biomédical",
    # Administratif d'exécution
    "standardiste", "agent d'accueil", "agent de facturation",
    "gestionnaire de stocks", "secrétaire médical",
]

# Mots-clés qui signalent un diplôme paramédical/médical obligatoire → reject
# Cherchés dans titre ET description
REJECT_PARAMEDICAL_KEYWORDS = [
    # Diplômes d'état
    "diplôme d'état infirmier", "diplome d'etat infirmier",
    "dei ", "d.e.i",
    "diplôme d'état aide-soignant", "diplôme d'état de sage-femme",
    "diplôme d'état de masseur", "diplôme d'état de manipulateur",
    "ibode", "iade", "cadre de santé",
    "auxiliaire de puériculture", "auxiliaire de puericulture",
    "electroradiologie", "électroradiologie",
    "dts manipulateur"
]

# Filières HCL connues à rejeter directement (labels exacts retournés par l'API)
# À compléter au fil de l'exploration via explore_hcl.py
REJECT_FILIERES = [
    "Infirmier",
    "Aide-soignant",
    "Sage-femme",
    "Rééducation",
    "Infirmier spécialisé",
    "Métiers du soin",
    "Secrétariat médical",
    "Pharmacie",
]

# Types de contrat à ignorer (labels exacts)
# Laisser vide pour l'instant — à affiner après exploration
REJECT_CONTRATS: list[str] = []


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _text(job: dict, *fields: str) -> str:
    """Concatène plusieurs champs en minuscules pour la recherche de mots-clés."""
    parts = [str(job.get(f) or "") for f in fields]
    return " ".join(parts).lower()


def _check_keywords(text: str, keywords: list[str]) -> str | None:
    """Retourne le premier mot-clé trouvé dans text, ou None."""
    for kw in keywords:
        if kw.lower() in text:
            return kw
    return None


# ─────────────────────────────────────────────
# FILTRES INDIVIDUELS
# ─────────────────────────────────────────────

def _auto_pass(job: dict) -> str | None:
    """
    Retourne une raison de pass si un mot-clé Bac+5 est détecté,
    None sinon.
    """
    text = _text(job, "titre", "description")
    kw = _check_keywords(text, PASS_KEYWORDS)
    if kw:
        return f"Auto-pass : mot-clé Bac+5 détecté ('{kw}')"
    return None


def _reject_filiere(job: dict) -> tuple[str, str] | None:
    filiere = str(job.get("filiere") or "").strip()   # ← champ natif, rien à parser
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
    """
    Retourne (categorie, raison) si le poste exige un diplôme
    paramédical ou médical, None sinon.
    """
    text = _text(job, "titre", "description")
    kw = _check_keywords(text, REJECT_PARAMEDICAL_KEYWORDS)
    if kw:
        return (
            "diplome_paramedical",
            f"Auto-reject paramédical : '{kw}' détecté",
        )
    return None


def _reject_filiere(job: dict) -> tuple[str, str] | None:
    """
    Retourne (categorie, raison) si la filière stockée est dans
    la liste de rejet, None sinon.
    Note : le champ 'filiere' n'est pas encore stocké en base —
    ce filtre sera actif une fois la colonne ajoutée.
    """
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


# ─────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────

def run_filter(conn, limit: int = None) -> dict:
    """
    Filtre les offres HCL actives sans décision IA.

    Args:
        conn    : connexion psycopg2 (fournie par le pipeline)
        limit   : nb max d'offres à traiter (debug)

    Returns:
        dict : { total, auto_passed, rejected, fallback_passed, errors }
    """
    jobs = get_offers_to_filter(conn)
    if limit:
        jobs = jobs[:limit]

    total = len(jobs)
    logger.info(f"Filtre HCL manuel — {total} offres à traiter")
    print(f"\n🔍 Filtre HCL — {total} offres à analyser...")

    stats = {
        "total": total,
        "auto_passed": 0,
        "rejected": 0,
        "fallback_passed": 0,
        "errors": 0,
    }

    for job in tqdm(jobs, desc="Filtre manuel HCL"):
        job_id = job["id"]
        titre = job.get("titre", "")[:60]

        try:
            # ── 1. Auto-pass Bac+5 ──────────────────────────────
            reason = _auto_pass(job)
            if reason:
                update_ai_filter(conn, job_id, "pass", reason)
                stats["auto_passed"] += 1
                logger.debug(f"  ✅ [{job_id}] {titre} — {reason}")
                continue

            # ── 2. Reject titre (surqualification) ──────────────
            result = _reject_title(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ [{job_id}] {titre} — {reason}")
                continue

            # ── 3. Reject paramédical ────────────────────────────
            result = _reject_paramedical(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ [{job_id}] {titre} — {reason}")
                continue

            # ── 4. Reject filière (si colonne dispo) ────────────
            result = _reject_filiere(job)
            if result:
                cat, reason = result
                update_ai_filter(conn, job_id, "reject", reason)
                stats["rejected"] += 1
                logger.debug(f"  ❌ [{job_id}] {titre} — {reason}")
                continue

            # ── [SLOT IA] ────────────────────────────────────────
            # TODO : appel LLM ici (même logique que filter_ai.py)
            # ────────────────────────────────────────────────────

            # ── 5. Fallback : passe par défaut ──────────────────
            update_ai_filter(conn, job_id, "pass", "Aucun filtre déclenché — passage par défaut")
            stats["fallback_passed"] += 1
            logger.debug(f"  🟡 [{job_id}] {titre} — fallback pass")

        except Exception as e:
            logger.error(f"  ⚠️  Erreur sur job {job_id} : {e}")
            stats["errors"] += 1

    # Résumé
    kept = stats["auto_passed"] + stats["fallback_passed"]
    ratio = (kept / total * 100) if total else 0
    print(f"\n📊 Résumé filtre HCL :")
    print(f"   Total analysées  : {total}")
    print(f"   ✅ Auto-passées  : {stats['auto_passed']}")
    print(f"   🟡 Fallback pass : {stats['fallback_passed']}")
    print(f"   ❌ Rejetées      : {stats['rejected']}")
    print(f"   ⚠️  Erreurs       : {stats['errors']}")
    print(f"   → Taux de rétention : {ratio:.1f}%")

    return stats


# ─────────────────────────────────────────────
# USAGE DIRECT (debug)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import psycopg2
    from database_hcl import get_connection

    logging.basicConfig(level=logging.DEBUG)

    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = get_connection(DATABASE_URL)
    try:
        stats = run_filter(conn, limit=50)
    finally:
        conn.close()