#config.py
import os

# --- URL cible ---
APHP_JOBS_URL = "https://recrutement.aphp.fr/api/search"

# --- Metiers exclus (filtre dur, avant LLM) ---
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
    "Technique - Autres métiers"
]

# --- Filieres exclues ---
EXCLUDED_FILIERES = [
    "Rééducation",
    "Paramédical encadrement",
]

# --- Mots-cles a exclure dans le titre ---
EXCLUDED_TITLE_REJECT_TITLE_KEYWORDS = [
    "formateur", "formatrice", "juriste",
    "médecin", "pharmacien", "chirurgien",
    "magasinier", "électricien", "plombier", "cuisinier",
    "agent de restauration", "brancardier", "agent de stérilisation",
    "technicien de maintenance", "agent logistique", "agent de service",
    "standardiste", "agent d'accueil", "agent de facturation",
    "gestionnaire de stocks", "agent d'entretien", "lingère",
    "chauffeur", "ambulancier",
    "technicien polyvalent", "technicien de maintenance",
    "technicien biomédical", "technicien de laboratoire",
    "technicien en recherche", "technicien d'information médicale",
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

# --- Email ---
EMAIL_SENDER    = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
SMTP_SERVER     = "smtp.gmail.com"
SMTP_PORT       = 587

PROFILE_FACTUEL = (
    "## PROFIL FACTUEL - NAIL MULATIER\n"
    "\n"
    "### Formation\n"
    "- Double diplome Centrale Lyon + DTU Danemark (programme TIME - Top International Managers in Engineering)\n"
    "- MSc Industrial Engineering & Management (DTU) + MSc Ingenieur Generaliste (Centrale Lyon)\n"
    "- GPA : 3.5/4 - Diplome septembre 2024\n"
    "- Cours cles : Optimisation (Programmation en Nombres Entiers, Stochastique), Business Analytics,\n"
    "  Supply Chain, Simulation, Gestion de projet avancee, Machine Learning\n"
    "\n"
    "### Experiences professionnelles\n"
    "\n"
    "Business Analyst - Picnic Technologies (8 mois, mai-dec 2025, Paris, CDI)\n"
    "- Analyse de donnees client pour des missions de consulting interne (SQL, dbt, GSheets)\n"
    "- Identification d opportunites commerciales et recommandations strategiques aux stakeholders\n"
    "- Lancement des livraisons du dimanche : modelisation des couts, alignement parties prenantes\n"
    "- Automatisation du reporting KPI d une campagne marketing 1M EUR (SQL/dbt, Tableau, temps reel)\n"
    "- Mise en production d outils via Docker et CI/CD (GitHub)\n"
    "- Fin de periode d essai - reconversion voulue vers le secteur hospitalier\n"
    "\n"
    "Operations Engineer & Data Analyst - Rigshospitalet Copenhague (8 mois, jan-aout 2024, stage master)\n"
    "- Projet de recherche operationnelle sur l optimisation de la planification des blocs operatoires\n"
    "- Developpement de modeles d optimisation stochastique (Python, Gurobi)\n"
    "- Analyse exploratoire de donnees hospitalieres complexes (Python, Pandas)\n"
    "- Simulation comparative des strategies (AnyLogic)\n"
    "- Resultats : potentiel de -20% de delais chirurgicaux, -15% de temps d inactivite\n"
    "- Contexte hospitalier avec exposition aux donnees medicales et aux enjeux des equipes soignantes\n"
    "\n"
    "Consultant - Hedon Associes (4 mois, avril-juillet 2022, Lyon, stage)\n"
    "- Missions de conseil en strategie et valorisation R&D pour des clients industriels\n"
    "- Valorisation financiere et fiscale de projets R&D (CIR, CII)\n"
    "- Redaction de dossiers techniques, veille technologique, etudes de marche\n"
    "\n"
    "### Competences techniques\n"
    "- Langages : Python (Pandas, NumPy, Sklearn, Matplotlib), SQL, R (notions)\n"
    "- Data & BI : dbt, Tableau, Power BI (notions), GSheets avance, Excel (tableaux croises, VBA si necessaire)\n"
    "- Optimisation & Simulation : Gurobi, AnyLogic, Programmation Stochastique\n"
    "- DevOps : Docker, GitHub, CI/CD\n"
    "- Gestion de projet : experience en ecole et en entreprise\n"
    "\n"
    "### Management\n"
    "- Encadrement informel en ecole (chef de projet, equipe de 5-6 personnes)\n"
    "- Lead technique sur des projets chez Picnic\n"
    "\n"
    "### Langues\n"
    "- Francais : natif\n"
    "- Anglais : professionnel complet (2 ans au Danemark, experience internationale)\n"
    "\n"
    "### Reseau APHP\n"
    "- Contact actif avec Alban Asmelli (DGA AP-HP Centre) - entretien realise\n"
    "- Contact regulier avec Lamya Ramdane (Cadre Administratif de DMU, Centrale Lyon)\n"
    "\n"
    "### Contraintes\n"
    "- Localisation : Paris intramuros et petite couronne\n"
    "- Disponibilite : immediate\n"
)

PROFILE_MOTIVATIONNEL = (
    "## PROFIL MOTIVATIONNEL - NAIL MULATIER\n"
    "\n"
    "### Vision long terme\n"
    "Evoluer vers des postes a hautes responsabilites dans le pilotage hospitalier\n"
    "(direction d unite, potentiellement direction d hopital via l EHESP).\n"
    "Rester proche du terrain tout en ayant un impact strategique.\n"
    "\n"
    "### Ce que je recherche dans un poste\n"
    "\n"
    "Ideal : combinaison data + terrain\n"
    "Le poste ideal combine une dimension analytique/technique (donnees, optimisation,\n"
    "pilotage) ET un contact avec les equipes soignantes ou operationnelles.\n"
    "Un poste purement data est acceptable comme premier pas dans le milieu hospitalier.\n"
    "Un poste purement administratif sans dimension analytique est a eviter.\n"
    "\n"
    "Missions concretes et bien definies\n"
    "J ai besoin de missions avec des objectifs clairs et mesurables.\n"
    "Les postes avec des missions floues ou centres sur l animation/formation sont a eviter.\n"
    "\n"
    "Impact reel et visible\n"
    "Je veux etre fier de contribuer aux soins publics.\n"
    "Les taches de recherche pure avec des objectifs abstraits sont peu motivantes.\n"
    "\n"
    "Interaction avec les equipes\n"
    "J apprécie d analyser des donnees en profondeur ET d interagir avec les equipes\n"
    "pour comprendre les enjeux terrain et presenter mes recommandations.\n"
    "\n"
    "### Criteres de selection par ordre de priorite\n"
    "1. Dimension analytique/data presente (meme partielle)\n"
    "2. Missions concretes avec objectifs mesurables\n"
    "3. Contact avec equipes soignantes ou operationnelles (forte preference)\n"
    "4. Potentiel d evolution vers des responsabilites (encadrement, pilotage)\n"
    "5. Localisation Paris intramuros (petite couronne acceptable)\n"
    "\n"
    "### Ce que je veux absolument eviter\n"
    "- Postes de recherche pure / academique (objectifs abstraits)\n"
    "- Postes de formation / accompagnement au changement sans dimension analytique\n"
    "- Missions tres floues sans perimetre defini\n"
    "- Postes 100% administratifs sans valeur ajoutee technique\n"
    "- Postes necessitant 5+ ans d experience hospitaliere francaise\n"
    "- Postes de direction trop seniors (directeur d hopital, DGA) - trop tot\n"
    "\n"
    "### Signaux positifs dans une offre\n"
    "- Mention de donnees, tableaux de bord, reporting, pilotage, optimisation\n"
    "- Contact avec DMU, blocs operatoires, services de soins\n"
    "- Poste de type charge de mission, cadre administratif, data analyst,\n"
    "  ingenieur, chef de projet avec dimension analytique\n"
    "- Equipe pluridisciplinaire melant soignants et administratifs\n"
    "- Possibilite d evolution mentionnee\n"
    "\n"
    "### Signaux negatifs dans une offre\n"
    "- Animation de formations, deploiement SI, accompagnement utilisateurs comme missions principales\n"
    "- Missions transversales sans contenu analytique precis\n"
    "- Experience hospitaliere de 5+ ans requise\n"
    "- Poste exclusivement en direction generale sans lien terrain\n"
)