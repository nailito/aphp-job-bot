import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── 3 CVs de base
CV_BASES = {
    "data": """
Naïl Mulatier — Analyste de données
EXPÉRIENCE :
- Business Analyst @ Picnic Technologie (2025, 6 mois) : Analyse SQL/GSheets, stratégies commerciales, reportings automatisés, Docker, CI/CD
- Data Analyst @ Slagelse Hospital, Danemark (2024, 7 mois) : Analyse systèmes hospitaliers Python/Power BI, modèles d'optimisation stochastique (Gurobi), simulation AnyLogic — réduction 20% retards, 15% inactivité
FORMATION :
- MSc Ingénierie Industrielle, spé. Recherche Opérationnelle — DTU Copenhague (2020-2024)
- Diplôme Ingénieur Généraliste — École Centrale de Lyon (2020-2024)
COMPÉTENCES : Python (Pandas, NumPy, Sklearn), SQL, Power BI, Tableau
LANGUES : Français, Anglais (parfait) | Japonais, Italien (bases)
""",

    "organisation": """
Naïl Mulatier — Ingénieur en Organisation
EXPÉRIENCE :
- Business Analyst Customer Team @ Picnic Technologie (2025, 6 mois CDI) : Lancement livraisons dominicales (modélisation coûts), analyse démographique zones de croissance, reporting SQL/dbt KPIs campagne 1M€ via Tableau
- Analyste Data & Planification Logistique @ Slagelse Hospital, Danemark (2024, 7 mois) : Analyse hospitalière Python/Power BI, optimisation planification salles opération (Gurobi), simulation AnyLogic — réduction 20% retards, 15% inactivité
FORMATION :
- MSc Ingénierie Industrielle et Management — DTU Copenhague (2020-2024)
- Diplôme Ingénieur Généraliste — École Centrale de Lyon (2020-2024)
  Projet : Chef de projet matériaux de santé → publication Materials Letters + Prix Francis Lebœuf 2021
COMPÉTENCES : Python, SQL, dbt, Power BI, Tableau, optimisation, simulation
LANGUES : Français, Anglais (parfait) | Japonais, Italien (bases)
""",

    "ro": """
Naïl Mulatier — Ingénieur en Recherche Opérationnelle
Ingénieur Centrale Lyon + DTU, spécialisé en optimisation mathématique et analyse de données pour la résolution de problèmes complexes de planification.
EXPÉRIENCE :
- Business Analyst @ Picnic Technologie (2025, 5 mois) : SQL, reporting automatisé, Docker, CI/CD
- Analyste Data & Ingénieur R.O. @ Slagelse Hospital (2024, 7 mois) : Analyse hospitalière Python, modèles R.O. (Programmation Stochastique, Gurobi), simulation AnyLogic — réduction 20% retards, 15% inactivité
FORMATION :
- MSc Ingénierie Industrielle, spé. R.O. — DTU Copenhague (2020-2024) : Integer Programming, healthcare management, networks optimization
- Diplôme Ingénieur Généraliste — École Centrale de Lyon (2020-2024)
COMPÉTENCES R.O. : Programmation Nombres Entiers, Génération de Colonnes, VRPTW, Métaheuristiques (LNS/CVRP), AnyLogic, Gurobi
COMPÉTENCES DATA : Python (Pandas, NumPy, Sklearn), SQL, Power BI
LANGUES : Français, Anglais (parfait) | Japonais, Italien (bases)
"""
}


def select_cv_base(job_title: str, job_description: str) -> tuple[str, str]:
    """Choisit le CV de base le plus adapté. Retourne (nom_base, texte_cv)."""
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""Tu dois choisir parmi ces 3 profils de CV lequel correspond le mieux à cette offre d'emploi.
Réponds UNIQUEMENT par un de ces mots : data, organisation, ro

Offre : {job_title}
Description : {job_description[:500]}

Profils disponibles :
- data : analyste de données, BI, reporting, SQL
- organisation : gestion de projet, organisation, logistique, planification
- ro : recherche opérationnelle, optimisation mathématique, modélisation

Réponds avec un seul mot."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )
    choice = response.choices[0].message.content.strip().lower()
    if choice not in CV_BASES:
        choice = "ro"  # fallback
    return choice, CV_BASES[choice]


def generate_cover_letter(job_title: str, job_description: str, hopital: str, cv_text: str) -> str:
    """Génère une lettre de motivation adaptée à l'offre."""
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""Tu es un expert en recrutement hospitalier. Rédige une lettre de motivation percutante et personnalisée pour Naïl Mulatier.

OFFRE :
Titre : {job_title}
Hôpital : {hopital}
Description : {job_description[:1500]}

CV DE BASE :
{cv_text}

CONSIGNES :
- Longueur : 3 paragraphes maximum, ton professionnel mais humain
- Paragraph 1 : accroche sur la mission de l'APHP + poste visé
- Paragraph 2 : 2-3 arguments concrets du CV qui matchent l'offre (avec chiffres si possible)
- Paragraph 3 : motivation pour l'APHP spécifiquement + appel à action
- NE PAS inventer de compétences absentes du CV
- Commencer par "Madame, Monsieur,"
- Terminer par "Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\nNaïl Mulatier"

Génère uniquement la lettre, sans commentaire."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


def adapt_cv(job_title: str, job_description: str, cv_text: str) -> str:
    """Adapte l'accroche et les points clés du CV à l'offre."""
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""Tu es un expert en recrutement. Adapte ce CV pour le poste suivant en modifiant UNIQUEMENT :
1. Le titre/accroche (1 ligne) pour matcher exactement le poste
2. La sélection et l'ordre des compétences pour mettre en avant celles pertinentes
3. Les bullets d'expérience : reformule pour mettre en valeur ce qui est pertinent pour ce poste

RÈGLES STRICTES :
- Ne jamais inventer d'expérience ou compétence absente
- Garder la même structure globale
- Rester factuel et concis

OFFRE :
Titre : {job_title}
Description : {job_description[:1000]}

CV ORIGINAL :
{cv_text}

Retourne uniquement le CV adapté en texte brut, formaté proprement."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct-0905",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()