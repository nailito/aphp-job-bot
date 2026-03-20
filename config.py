# ============================================================
#  config.py  —  À PERSONNALISER avant de lancer le bot
# ============================================================

# --- Ton profil professionnel -----------------------------------
# Plus c'est détaillé, meilleur sera le matching !
PROFILE = """
Profession : Infirmier(ère) diplômé(e) d'état
Expérience : 5 ans en service de médecine interne et urgences
Compétences clés : soins infirmiers, gestion de la douleur, soins palliatifs,
                   éducation thérapeutique, coordination pluridisciplinaire
Formation complémentaire : DU plaies et cicatrisation
Localisation souhaitée : Paris et Île-de-France (petite couronne acceptée)
Type de contrat souhaité : CDI ou CDD long terme
Temps de travail : temps plein ou 80%
Ce que je recherche : un service dynamique avec des projets de soins innovants,
                      possibilités de formation continue
Ce que je veux éviter : gardes de nuit exclusives, très longues distances
"""

# --- Seuil de pertinence (0 à 10) ------------------------------
# Les offres avec un score >= à ce seuil seront incluses dans le rapport
MIN_SCORE = 6

# --- Nombre max d'offres dans l'email --------------------------
MAX_OFFERS_IN_EMAIL = 15

# --- Email -----------------------------------------------------
EMAIL_SENDER    = "ton.adresse@gmail.com"      # Expéditeur (ton Gmail)
EMAIL_PASSWORD  = ""                            # App password Gmail (voir README)
EMAIL_RECIPIENT = "ton.adresse@gmail.com"      # Destinataire (toi-même)
SMTP_SERVER     = "smtp.gmail.com"
SMTP_PORT       = 587

# --- Clé API Anthropic ------------------------------------------
# Ne mets JAMAIS ta clé ici en clair si tu utilises GitHub !
# Elle sera lue depuis les variables d'environnement (voir README)
import os
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- URL cible --------------------------------------------------
APHP_JOBS_URL = "https://recrutement.aphp.fr/jobs"
