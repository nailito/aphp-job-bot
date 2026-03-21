import os

# --- URL cible ---
APHP_JOBS_URL = "https://recrutement.aphp.fr/api/search"

# --- Métiers exclus (filtre dur, avant LLM) ---
EXCLUDED_METIERS = [
    "Infirmier", "Psychologue", "Aide-soignant",
    "Technicien de laboratoire", "Infirmier puériculteur",
    "Encadrement Maïeutique", "Infirmier de bloc", "Auxiliaire de puériculture",
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
    "Accueil - Standard - Call center"
]

EXCLUDED_FILIERES = [
    "Rééducation",
    "Paramédical encadrement",
]

# --- Mots-clés à exclure dans le titre (filtre dur) ---
EXCLUDED_TITLE_KEYWORDS = [
    "formateur", "formatrice", "juriste",
    "médecin", "pharmacien", "chirurgien",
]

# --- Localisation acceptée (filtre dur) ---
ACCEPTED_LOCATIONS = ["Paris"]  # Filtre souple : on garde si "Paris" est dans la location

# --- Seuil de score LLM ---
MIN_SCORE = 50  # On envoie par email uniquement les offres >= 50/100

# --- Nombre max d'offres dans l'email ---
MAX_OFFERS_IN_EMAIL = 20

# --- API ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Email ---
EMAIL_SENDER    = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
SMTP_SERVER     = "smtp.gmail.com"
SMTP_PORT       = 587

# --- Profil candidat complet (injecté dans le prompt LLM) ---
PROFILE = """
## PROFIL CANDIDAT : Naïl Mulatier

**Formation :** Double diplôme Centrale Lyon + DTU (Danemark)
Spécialisation : Management Industriel, Recherche Opérationnelle, Analyse de Données

**Expériences :**
- Mémoire de master : optimisation planification blocs opératoires (2 hôpitaux danois, 20 salles)
  → Python, R, Gurobi, AnyLogic, modèles stochastiques → -20% retards, -15% inactivité
- Business Analyst chez Picnic Technologies : SQL, Python, Power BI, Tableau, Docker, CI/CD
- Stage consultant Hédon Associés : conseil stratégie, évaluation financière R&D

**Compétences techniques :** Python, R, SQL, Power BI, Tableau, Gurobi, Docker, Git, AnyLogic

**Contraintes :** Paris intramuros uniquement | Salaire min 38k€ | Disponible immédiatement

---

## TYPES DE POSTES RECHERCHÉS

**PRIORITÉ 1 — EXCELLENT MATCH (mots-clés : +30 pts chacun)**
data scientist, data analyst, statisticien, analyste données, ingénieur data,
business intelligence, BI, PMSI, DIM, entrepôt données santé, SQL, Python, R, SAS

**PRIORITÉ 2 — BON MATCH (mots-clés : +15 pts chacun)**
cadre administratif DMU, contrôle de gestion, performance, pilotage médico-économique,
tableaux de bord, indicateurs, EPRD, bloc opératoire, plateau technique, ingénieur hospitalier

**PRIORITÉ 3 — MATCH MOYEN (mots-clés : +10 pts chacun)**
chef de projet, transformation, optimisation, flux, parcours patient,
amélioration continue, lean, programmation des soins

---

## POSTES À EXCLURE (score automatiquement < 50)
- Postes purement juridiques / paramédicaux / médicaux

---

## GRILLE DE SCORING (sur 100)

| Critère | Points |
|---|---|
| Mention data, statistique, analyse, BI, PMSI | 30 |
| Mention Python, R, SQL, SAS, programmation | 20 |
| Mention bloc opératoire, plateau, flux, optimisation | 15 |
| Mention pilotage, performance, contrôle de gestion, tableaux de bord | 15 |
| Niveau bac+5 / master / ingénieur | 10 |
"""