"""
cover_letter.py — Génération de lettre de motivation via Groq kimi-k2

Approche : on donne au modèle exactement ce qu'on donnerait à une IA manuellement :
  - L'offre d'emploi complète
  - Le CV de base sélectionné
  - Une LM exemple réussie (référence de style)
  → Le modèle génère une LM adaptée à l'offre, dans le même style.
"""

import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# ---------------------------------------------------------------------------
# CV de base — 3 versions selon le type de poste
# ---------------------------------------------------------------------------
CV_BASES = {
    "data": """Naïl Mulatier — Analyste de données
115 rue de Meaux, 75019 Paris | nail.mulatier@orange.fr | +33 6 73 83 31 40

EXPÉRIENCE PROFESSIONNELLE

2025 — 6 mois | Business Analyst | Picnic Technologies, Paris
- Analyse de données (SQL, GSheets) pour identifier les opportunités et élaborer des stratégies commerciales.
- Gestion intégrale des projets : de la définition des objectifs à l'implémentation des solutions.
- Monitorage de la performance via des reportings automatisés (Power BI). Mise en production via Docker et CI/CD GitHub.

2024 — 7 mois | Data Analyst | Mémoire de Master — Slagelse Hospital, Copenhague
- Analyse des systèmes hospitaliers (région Sjælland) : Python (exploration), Power BI (visualisation).
- Modèles d'optimisation (Programmation Stochastique / Gurobi) et simulation (AnyLogic) pour la planification des blocs opératoires.
- Résultats : réduction potentielle de 20 % des retards et 15 % du temps d'inactivité.

FORMATION
2020–2024 | Danmarks Tekniske Universitet (DTU), Copenhague — MSc Ingénierie Industrielle, spécialisation Recherche Opérationnelle
2020–2024 | École Centrale de Lyon — Diplôme d'Ingénieur Généraliste

COMPÉTENCES
- Analyse de données : Python (Pandas, NumPy, Sklearn), SQL, Power BI, Tableau
- Recherche Opérationnelle : Programmation en Nombres Entiers, Métaheuristiques, Simulation (AnyLogic)
- Langues : Français et Anglais (bilingue), Japonais et Italien (bases)""",

    "organisation": """Naïl Mulatier — Ingénieur en Organisation
115 rue de Meaux, 75019 Paris | nail.mulatier@orange.fr | +33 6 73 83 31 40

EXPÉRIENCE PROFESSIONNELLE

2025 — 6 mois | Business Analyst | Picnic Technologies, Paris
- Pilotage de projets transversaux : définition des objectifs, coordination des équipes, implémentation des solutions.
- Transformation d'un processus défaillant : diagnostic, proposition d'une nouvelle organisation, conduite du changement auprès de deux équipes réticentes, déploiement réussi.
- Création de reportings automatisés (Power BI) pour le suivi de la performance opérationnelle.

2024 — 7 mois | Chef de projet / Analyste | Mémoire de Master — Slagelse Hospital, Copenhague
- Analyse organisationnelle de 20 blocs opératoires : identification des dysfonctionnements (rigidité des plannings, dépassements d'horaires, manque d'adaptabilité aux urgences).
- Proposition de solutions validées par simulation, présentées aux équipes hospitalières.

2023 — 4 mois | Consultant Stagiaire | Hédon Associés, Paris
- Missions de conseil en stratégie à forte valeur ajoutée, travail transversal avec différentes équipes.

FORMATION
2020–2024 | Danmarks Tekniske Universitet (DTU), Copenhague — MSc Ingénierie Industrielle, spécialisation Recherche Opérationnelle
2020–2024 | École Centrale de Lyon — Diplôme d'Ingénieur Généraliste

COMPÉTENCES
- Gestion de projet, conduite du changement, pilotage de la performance
- Analyse de données : Python, SQL, Power BI
- Langues : Français et Anglais (bilingue), Japonais et Italien (bases)""",

    "ro": """Naïl Mulatier — Ingénieur Recherche Opérationnelle
115 rue de Meaux, 75019 Paris | nail.mulatier@orange.fr | +33 6 73 83 31 40

EXPÉRIENCE PROFESSIONNELLE

2024 — 7 mois | Ingénieur R.O. | Mémoire de Master — Slagelse Hospital, Copenhague
- Modélisation et résolution de problèmes d'optimisation pour la planification des blocs opératoires (20 salles, région Sjælland).
- Modèles : Programmation Stochastique, résolu avec Gurobi. Simulation des stratégies sous AnyLogic.
- Réduction potentielle de 20 % des retards et 15 % du temps d'inactivité.

2025 — 6 mois | Business Analyst | Picnic Technologies, Paris
- Optimisation de processus métiers par l'analyse de données (Python, SQL).
- Création d'outils de suivi de la performance et de reporting automatisé (Power BI).

FORMATION
2020–2024 | Danmarks Tekniske Universitet (DTU), Copenhague — MSc Ingénierie Industrielle, spécialisation Recherche Opérationnelle
Cours : Programmation en Nombres Entiers, Génération de Colonnes, VRPTW, Métaheuristiques (LNS pour CVRP), Simulation en gestion des opérations, Optimisation des réseaux...
2020–2024 | École Centrale de Lyon — Diplôme d'Ingénieur Généraliste

COMPÉTENCES
- R.O. : Programmation en Nombres Entiers, Métaheuristiques, Simulation (AnyLogic), Gurobi
- Python (Pandas, NumPy, Sklearn), SQL, Power BI
- Langues : Français et Anglais (bilingue)""",
}

# ---------------------------------------------------------------------------
# LM de référence — style et structure à reproduire
# ---------------------------------------------------------------------------
LM_REFERENCE = """Madame,

Diplômé de l'École Centrale de Lyon et de l'Université Technique du Danemark (DTU) en management industriel, je vous adresse ma candidature pour le poste de chargé de mission parcours administratif du patient au sein du GHU Paris Centre.

J'ai effectué mon mémoire de master sur la planification et programmation des salles d'opération pour deux hôpitaux danois, sous la direction du Professeur Jens O. Brunner. Durant ces sept mois, j'ai analysé les données opératoires réelles de 20 salles, identifié des dysfonctionnements organisationnels (faible adaptabilité face aux urgences, planifications rigides générant des heures supplémentaires) et proposé des solutions validées par simulation. Cette première expérience hospitalière a confirmé mon souhait d'évoluer dans ce secteur et m'a permis d'appréhender le niveau de rigueur et de complexité qu'il requiert.

J'ai occupé un poste de consultant Business Analyst chez Picnic Technologies, où j'ai mené de nombreuses analyses de bases de données (Python, SQL), piloté plusieurs projets et créé des reportings automatisés (Power BI). Un de mes projets a consisté en la transformation d'un processus source de plaintes et de charge de travail excessive. J'ai proposé une nouvelle organisation, l'ai testée avec succès, puis accompagné deux équipes initialement réticentes dans son déploiement.

Ce poste répond à mon projet professionnel : allier travail de terrain au contact des services de soins et pilotage de projets transversaux mobilisant de multiples parties prenantes. Les perspectives d'évolution vers la Direction des Opérations renforcent mon intérêt pour ce poste.

Je vous remercie de l'attention que vous porterez à ma candidature et je me réjouis d'avoir l'occasion de m'entretenir avec vous de mes qualifications et de la manière dont je peux contribuer au succès de ce projet de transformation.

Veuillez agréer, Madame, l'expression de mes salutations distinguées.

Naïl Mulatier"""

# ---------------------------------------------------------------------------
# Prompt système
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Tu es un expert en rédaction de lettres de motivation pour des postes dans le secteur hospitalier et la fonction publique (AP-HP).

Tu dois générer une lettre de motivation pour Naïl Mulatier, en t'appuyant sur :
1. Son CV (fourni)
2. Une lettre de motivation exemple réussie (fournie) — c'est la référence de style, structure et ton
3. L'offre d'emploi ciblée (fournie)

Règles strictes :
- 4 paragraphes : (1) accroche diplômes + expérience la plus pertinente pour ce poste, (2) deuxième expérience pertinente avec exemple concret, (3) motivation spécifique au poste et à l'établissement, (4) formule de clôture
- Commence par "Madame," (ou "Monsieur," si le genre est clairement identifiable dans l'offre)
- Style : direct, concret, professionnel — pas de tournures creuses ni d'adjectifs vides
- Chaque paragraphe doit mentionner des éléments précis issus de l'offre (missions, outils, contexte)
- Termine par "Veuillez agréer, Madame [ou Monsieur], l'expression de mes salutations distinguées.\\n\\nNaïl Mulatier"
- NE réutilise PAS mot pour mot la LM exemple — inspire-toi uniquement du style et de la structure
- Renvoie UNIQUEMENT le texte de la lettre, sans commentaires, sans titre, sans balises"""

# ---------------------------------------------------------------------------
# select_cv_base — appelé par le dashboard
# ---------------------------------------------------------------------------
def select_cv_base(job_title: str, job_description: str) -> tuple[str, str]:
    """
    Choisit le CV de base le plus adapté à l'offre parmi data / organisation / ro.

    Returns:
        (base_name, cv_text) — ex: ("data", "Naïl Mulatier — Analyste de données...")
    """
    prompt = f"""Voici un intitulé de poste et sa description.
Choisis parmi ces trois profils CV celui qui correspond le mieux :
- "data" : poste orienté analyse de données, reporting, SQL, Python, dashboards
- "organisation" : poste orienté gestion de projet, conduite du changement, coordination, pilotage
- "ro" : poste orienté optimisation, modélisation, recherche opérationnelle, algorithmes

Réponds UNIQUEMENT par un mot parmi : data, organisation, ro

Intitulé : {job_title}
Description : {job_description[:800]}"""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10,
    )
    base_name = response.choices[0].message.content.strip().lower()
    if base_name not in CV_BASES:
        base_name = "organisation"  # fallback par défaut

    return base_name, CV_BASES[base_name]


# ---------------------------------------------------------------------------
# generate_cover_letter — appelé par le dashboard
# Signature exacte : (job_title, job_description, hopital, cv_text) → str
# ---------------------------------------------------------------------------
def generate_cover_letter(
    job_title: str,
    job_description: str,
    hopital: str,
    cv_text: str,
) -> str:
    """
    Génère une lettre de motivation adaptée à une offre d'emploi.

    Returns:
        str : texte brut de la lettre, prêt à copier-coller dans un traitement de texte
    """
    user_message = f"""Voici les éléments pour générer la lettre de motivation :

---
MON CV :
{cv_text}

---
MA LETTRE DE MOTIVATION EXEMPLE (style et structure à respecter) :
{LM_REFERENCE}

---
OFFRE D'EMPLOI :
Intitulé : {job_title}
Établissement : {hopital}

Description :
{job_description}

---
Génère la lettre de motivation adaptée à cette offre."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.35,
        max_tokens=1200,
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# adapt_cv — appelé par le dashboard
# ---------------------------------------------------------------------------
def adapt_cv(
    job_title: str,
    job_description: str,
    cv_base_text: str,
) -> str:
    """
    Adapte légèrement le CV de base pour mettre en avant les éléments
    les plus pertinents pour l'offre ciblée.

    Returns:
        str : texte du CV adapté, prêt à copier-coller
    """
    prompt = f"""Tu es un expert en rédaction de CV pour le secteur hospitalier.

Voici un CV de base et une offre d'emploi. Adapte le CV en :
- Réordonnant ou reformulant les bullet points pour mettre en avant ce qui correspond à l'offre
- Ajustant l'intitulé du poste visé si pertinent
- Ne supprimant aucune expérience, ne rajoutant rien d'inventé
- Gardant exactement le même format texte

CV DE BASE :
{cv_base_text}

OFFRE :
Intitulé : {job_title}
Description : {job_description[:1000]}

Renvoie UNIQUEMENT le texte du CV adapté, sans commentaires."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=900,
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# text_to_pdf — retourne le texte brut encodé UTF-8
# Compatible avec st.download_button (mime="text/plain")
# Pas de dépendance FPDF — copier-coller dans un traitement de texte ensuite
# ---------------------------------------------------------------------------
def text_to_pdf(text: str, is_lm: bool = True) -> bytes:
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Test direct : python cover_letter.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_title = "Chargé de mission transformation numérique"
    test_hopital = "AP-HP Lariboisière"
    test_description = """
Rattaché(e) à la Direction des Systèmes d'Information, vous participez à la conduite
de projets de transformation numérique.

Missions :
- Déploiement de nouveaux outils numériques (DPI, logiciels métiers)
- Analyse de données pour mesurer l'impact des projets
- Animation de groupes de travail pluridisciplinaires
- Rédaction de tableaux de bord et rapports d'avancement
- Conduite du changement auprès des équipes

Profil : Bac+5 ingénieur ou master, expérience en analyse de données (Python, SQL, Power BI),
capacité à travailler en transversal, rigueur, autonomie.
"""

    print("🔍 Sélection du CV de base...")
    base_name, cv_text = select_cv_base(test_title, test_description)
    print(f"   → CV sélectionné : {base_name}\n")

    print("✍️  Génération de la lettre de motivation...\n")
    lm = generate_cover_letter(test_title, test_description, test_hopital, cv_text)
    print(lm)