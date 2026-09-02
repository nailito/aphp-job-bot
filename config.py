# config.py
import os
from pathlib import Path

# --- URL cible ---
APHP_JOBS_URL = "https://recrutement.aphp.fr/api/search"

# --- Metiers exclus (filtre dur, avant LLM) ---
EXCLUDED_METIERS = [
    "Infirmier",
    "Psychologue",
    "Aide-soignant",
    "Technicien de laboratoire",
    "Infirmier puériculteur",
    "Encadrement Maïeutique",
    "Infirmier de bloc",
    "Auxiliaire de puériculture",
    "Assistanat secrétariat - secrétariat",
    "Responsable RH - Encadrant RH",
    "Secrétariat médical - Assistanat médical",
    "Soins, paramédical - Autres métiers",
    "Infirmier de bloc - IBO-IBODE",
    "Qualité Hygiène",
    "Cuisinier - Agent de restauration- Hôtellerie",
    "Administration RH - chargé de/gestionnaire RH",
    "Assistant Social",
    "Educateur - Moniteur - Animateur",
    "Infirmier- Autres métiers",
    "Secrétariat médical - Assistanat médical",
    "Infirmier puériculteur",
    "Brancardier",
    "Diététicien - Diététique",
    "Ambulancier",
    "Formateur - Cadre formateur",
    "Paie",
    "Médecin",
    "Management socio-éducatif",
    "Accueil - Standard - Call center",
    "ARC- TECH Attaché/technicien en recherche Clinique",
    "Comptabilité - Facturation - Régie",
    "Infirmier Pratique Avancée - IPA",
    "Maïeutique",
    "Maintenance - Travaux",
    "Manipulateur en électroradiologie",
    "Préparateur en pharmacie",
    "Sécurité au travail et environnement",
    "Socio-éducatif - Autres métiers",
    "Support et Exploitation",
    "Technique - Autres métiers",
]

# --- Filieres exclues ---
EXCLUDED_FILIERES = [
    "Rééducation",
    "Paramédical encadrement",
]

# --- Mots-cles a exclure dans le titre ---
EXCLUDED_TITLE_REJECT_TITLE_KEYWORDS = [
    "formateur",
    "formatrice",
    "juriste",
    "médecin",
    "pharmacien",
    "chirurgien",
    "magasinier",
    "électricien",
    "plombier",
    "cuisinier",
    "agent de restauration",
    "brancardier",
    "agent de stérilisation",
    "technicien de maintenance",
    "agent logistique",
    "agent de service",
    "standardiste",
    "agent d'accueil",
    "agent de facturation",
    "gestionnaire de stocks",
    "agent d'entretien",
    "lingère",
    "chauffeur",
    "ambulancier",
    "technicien polyvalent",
    "technicien de maintenance",
    "technicien biomédical",
    "technicien de laboratoire",
    "technicien en recherche",
    "technicien d'information médicale",
    "enseignant en activités physiques",
]

# --- Contrats exclus ---
EXCLUDED_CONTRATS = ["Stage", "CAE"]

# --- Localisation acceptee ---
ACCEPTED_LOCATIONS = ["Paris"]

# --- Seuil de score ---
MIN_SCORE = 50

# --- Nombre max d'offres dans l'email ---
MAX_OFFERS_IN_EMAIL = 20

# --- API ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def _load_private_text(value_env: str, file_env: str) -> str:
    """Load private prompt context from an environment variable or a local file."""
    value = os.getenv(value_env, "").strip()
    if value:
        return value

    file_path = os.getenv(file_env, "").strip()
    if not file_path:
        return ""

    return Path(file_path).expanduser().read_text(encoding="utf-8").strip()


# Candidate details stay outside the repository. GitHub Actions can inject the two
# text values as encrypted secrets; local runs can point to ignored Markdown files.
PROFILE_FACTUEL = _load_private_text("PROFILE_FACTUEL", "PROFILE_FACTUEL_FILE")
PROFILE_MOTIVATIONNEL = _load_private_text("PROFILE_MOTIVATIONNEL", "PROFILE_MOTIVATIONNEL_FILE")
