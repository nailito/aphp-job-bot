"""
cover_letter.py — Génération de lettre de motivation via Groq kimi-k2

Approche : on donne au modèle exactement ce qu'on donnerait à une IA manuellement :
  - L'offre d'emploi complète
  - Le CV de base (un seul)
  - Une LM exemple réussie (référence de style)
  → Le modèle génère une LM adaptée à l'offre, dans le même style.
"""

import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# ---------------------------------------------------------------------------
# CV de référence
# ---------------------------------------------------------------------------
CV_BASE = """Naïl Mulatier — Analyste de données
115 rue de Meaux, 75019 Paris | nail.mulatier@orange.fr | +33 6 73 83 31 40

EXPÉRIENCE PROFESSIONNELLE

2025 — 6 mois | Business Analyst | Picnic Technologies, Paris
- Analyse de données (SQL, GSheets) pour identifier les opportunités et élaborer des stratégies commerciales. Communication de ces analyses et des recommandations aux parties prenantes.
- Gestion intégrale des projets, couvrant la définition des objectifs à l'implémentation des solutions.
- Monitorage continu de la performance via la création de reportings automatisés. Mise en production des outils assurée par la conteneurisation (Docker) et l'intégration continue (GitHub/CI/CD).

2024 — 7 mois | Data Analyst | Mémoire de Master — Slagelse Hospital, Copenhague
Operating room planning and scheduling using data analytics and operations research techniques.
- Conduit l'analyse approfondie des systèmes hospitaliers (région Sjælland), utilisant Python (exploration) et Power BI (visualisation).
- Développé et résolu des modèles d'Optimisation (Programmation Stochastique / Gurobi), puis simulé les stratégies testées (AnyLogic) pour la planification des salles d'opération.
- L'évaluation comparative a permis d'identifier un potentiel de réduction de 20% des retards et de 15% du temps d'inactivité (gain d'efficacité opérationnelle).

FORMATION
2020–2024 | Danmarks Tekniske Universitet (DTU), Copenhague
MSc en Ingénierie Industrielle, spécialisation en recherche opérationnelle.
Cours notables : Programmation en Nombres Entiers, Optimisation des transports,
Optimisation des Réseaux, Simulation en gestion des opérations, Analyse de la chaîne
d'approvisionnement, Industrie 4.0 en gestion des opérations…

2020–2024 | École Centrale de Lyon (ECL), Lyon
Diplôme d'Ingénieur Généraliste
Cours notables : Informatique, mathématique, sciences économiques et sociales.

COMPÉTENCES
- Analyse de données : Python (Pandas, NumPy, Sklearn), SQL, Power BI, Tableau
- Recherche Opérationnelle : Programmation en Nombres Entiers, Génération de Colonnes, VRPTW,
  Métaheuristiques (LNS pour CVRP), Modèles de Simulation (AnyLogic)
- Langues : Français et Anglais (bilingue), Japonais et Italien (bases)"""

# ---------------------------------------------------------------------------
# LM de référence — style et structure à reproduire
# ---------------------------------------------------------------------------
LM_REFERENCE = """Madame, Monsieur,

Diplômé de l'École Centrale de Lyon et de l'Université Technique du Danemark (DTU) en management industriel, je vous adresse ma candidature pour le poste de chargé de mission parcours administratif du patient au sein du GHU Paris Centre. J'ai effectué mon mémoire de master sur la planification et programmation des salles d'opération pour deux hôpitaux danois, sous la direction du Professeur Jens O. Brunner. Durant ces sept mois, j'ai analysé les données opératoires réelles de 20 salles, identifié des dysfonctionnements organisationnels (faible adaptabilité face aux urgences, planifications rigides générant des heures supplémentaires) et proposé des solutions validées par simulation. Cette première expérience hospitalière a confirmé mon souhait d'évoluer dans ce secteur et m'a permis d'appréhender le niveau de rigueur et de complexité qu'il requiert.

J'ai occupé un poste de consultant Business Analyst chez Picnic Technologies, où j'ai mené de nombreuses analyses de bases de données (Python, SQL), piloté plusieurs projets et créé des reportings automatisés (Power BI). Un de mes projets a consisté en la transformation d'un processus source de plaintes et de charge de travail excessive. J'ai proposé une nouvelle organisation, l'ai testée avec succès, puis accompagné deux équipes initialement réticentes dans son déploiement. J'ai par ailleurs effectué un stage de 4 mois chez Hédon Associés, un cabinet de conseil en stratégie, où j'ai participé à des missions de conseil à forte valeur ajoutée et développé ma capacité à travailler en transversal avec différentes équipes.

Ce poste répond à mon projet professionnel : allier travail de terrain au contact des services de soins et pilotage de projets transversaux mobilisant de multiples parties prenantes. Mes échanges avec M. Alban Asmelli et Mme Lamya Ramdane, cadre administratif de DMU et ancienne élève de Centrale Lyon, ont confirmé que l'AP-HP Centre est l'environnement dans lequel je souhaite évoluer. Les perspectives d'évolution vers la Direction des Opérations renforcent mon intérêt pour ce poste.

Je vous remercie de l'attention que vous porterez à ma candidature et je me réjouis d'avoir l'occasion de m'entretenir avec vous de mes qualifications et de la manière dont je peux contribuer au succès de ce projet de transformation.

Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

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
- Commence par "Madame, Monsieur,"
- Style : direct, concret, professionnel — pas de tournures creuses ni d'adjectifs vides
- Chaque paragraphe doit mentionner des éléments précis issus de l'offre (missions, outils, contexte)
- Termine par "Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\\n\\nNaïl Mulatier"
- NE réutilise PAS mot pour mot la LM exemple — inspire-toi uniquement du style et de la structure
- Renvoie UNIQUEMENT le texte de la lettre, sans commentaires, sans titre, sans balises"""


# ---------------------------------------------------------------------------
# generate_cover_letter — appelé par le dashboard
# Signature : (job_title, job_description, hopital, cv_text) → str
# ---------------------------------------------------------------------------
def generate_cover_letter(
    job_title: str,
    job_description: str,
    hopital: str,
    cv_text: str = CV_BASE,
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

    lm = generate_cover_letter(test_title, test_description, test_hopital)
    print(lm)