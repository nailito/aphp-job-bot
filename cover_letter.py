import os
from groq import Groq
from fpdf import FPDF
import io



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
        model="moonshotai/kimi-k2-instruct-0905",
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
        model="moonshotai/kimi-k2-instruct-0905",
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



def text_to_pdf(text: str, is_lm: bool = False) -> bytes:
    """Convertit un texte en PDF avec police FreeSerif (Times-like, Unicode)."""
    import os
    from datetime import datetime

    MOIS_FR = {
        "January": "janvier", "February": "février", "March": "mars",
        "April": "avril", "May": "mai", "June": "juin",
        "July": "juillet", "August": "août", "September": "septembre",
        "October": "octobre", "November": "novembre", "December": "décembre"
    }

    FONT_SIZE = 12      # taille unique pour tout le document
    LINE_H = 7          # hauteur de ligne corps
    HEADER_LINE_H = 6   # hauteur de ligne en-tête
    INDENT = 10         # alinéa 1ère ligne (~1 cm)
    PARA_SPACE = 5      # espace entre paragraphes

    base = os.path.join(os.path.dirname(__file__), "fonts")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=20)

    pdf.add_font("FreeSerif", "",   os.path.join(base, "FreeSerif.ttf"))
    pdf.add_font("FreeSerif", "B",  os.path.join(base, "FreeSerifBold.ttf"))
    pdf.add_font("FreeSerif", "I",  os.path.join(base, "FreeSerifItalic.ttf"))
    pdf.add_font("FreeSerif", "BI", os.path.join(base, "FreeSerifBoldItalic.ttf"))

    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    if is_lm:
        # ── Nom en gras + souligné
        pdf.set_font("FreeSerif", "B", FONT_SIZE)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, HEADER_LINE_H, text="Naïl Mulatier", new_x="LMARGIN", new_y="NEXT")

        # Soulignement manuel sous le nom
        y_underline = pdf.get_y()
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        name_width = pdf.get_string_width("Naïl Mulatier")
        pdf.line(pdf.l_margin, y_underline, pdf.l_margin + name_width, y_underline)
        pdf.ln(1)

        # ── Coordonnées (même taille 12pt)
        pdf.set_font("FreeSerif", "", FONT_SIZE)
        pdf.cell(0, HEADER_LINE_H, text="+33 6 73 83 31 40", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, HEADER_LINE_H, text="nail.mulatier@orange.fr", new_x="LMARGIN", new_y="NEXT")

        # ── Date alignée à droite
        pdf.ln(10)
        now = datetime.now()
        mois = MOIS_FR.get(now.strftime("%B"), now.strftime("%B"))
        date_str = f"Paris, le {now.day} {mois} {now.year}"
        pdf.set_font("FreeSerif", "", FONT_SIZE)
        pdf.cell(page_width, HEADER_LINE_H, text=date_str, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

    # ── Corps du texte
    pdf.set_font("FreeSerif", "", FONT_SIZE)
    paragraphs = text.split("\n\n")

    for i, para in enumerate(paragraphs):
        lines = para.strip().split("\n")
        for j, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Alinéa uniquement sur la 1ère ligne de chaque paragraphe (sauf le tout premier)
            use_indent = (j == 0 and i > 0)
            available_width = page_width - (INDENT if use_indent else 0)

            # Découper la ligne en sous-lignes manuellement pour contrôler l'indent
            words = line.split(" ")
            current_line = ""
            first_line_of_para = True

            for word in words:
                test = (current_line + " " + word).strip()
                w = page_width - (INDENT if (use_indent and first_line_of_para) else 0)
                if pdf.get_string_width(test) <= w:
                    current_line = test
                else:
                    # Imprimer la ligne courante
                    if use_indent and first_line_of_para:
                        pdf.cell(INDENT)
                        first_line_of_para = False
                    pdf.cell(0, LINE_H, text=current_line, new_x="LMARGIN", new_y="NEXT")
                    current_line = word

            # Dernière ligne du segment
            if current_line:
                if use_indent and first_line_of_para:
                    pdf.cell(INDENT)
                pdf.multi_cell(0, LINE_H, text=current_line)

        pdf.ln(PARA_SPACE)

    return bytes(pdf.output())
    """Convertit un texte en PDF avec police FreeSerif (Times-like, Unicode)."""
    import os
    from datetime import datetime

    # Mapping mois anglais → français (strftime est locale-dépendant sur les serveurs)
    MOIS_FR = {
        "January": "janvier", "February": "février", "March": "mars",
        "April": "avril", "May": "mai", "June": "juin",
        "July": "juillet", "August": "août", "September": "septembre",
        "October": "octobre", "November": "novembre", "December": "décembre"
    }

    base = os.path.join(os.path.dirname(__file__), "fonts")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(25, 25, 25)
    pdf.set_auto_page_break(auto=True, margin=20)

    pdf.add_font("FreeSerif", "",   os.path.join(base, "FreeSerif.ttf"))
    pdf.add_font("FreeSerif", "B",  os.path.join(base, "FreeSerifBold.ttf"))
    pdf.add_font("FreeSerif", "I",  os.path.join(base, "FreeSerifItalic.ttf"))
    pdf.add_font("FreeSerif", "BI", os.path.join(base, "FreeSerifBoldItalic.ttf"))

    page_width = pdf.w - pdf.l_margin - pdf.r_margin  # largeur utile

    if is_lm:
        # ── En-tête gauche : Nom en gras
        pdf.set_font("FreeSerif", "B", 12)
        pdf.cell(0, 7, text="Naïl Mulatier", new_x="LMARGIN", new_y="NEXT")

        # ── Coordonnées (interlignes légèrement réduits)
        pdf.set_font("FreeSerif", "", 11)
        pdf.cell(0, 6, text="+33 6 73 83 31 40", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, text="nail.mulatier@orange.fr", new_x="LMARGIN", new_y="NEXT")

        # ── Date alignée à DROITE
        pdf.ln(10)
        now = datetime.now()
        mois = MOIS_FR.get(now.strftime("%B"), now.strftime("%B"))
        date_str = f"Paris, le {now.day} {mois} {now.year}"
        pdf.set_font("FreeSerif", "", 11)
        pdf.cell(page_width, 6, text=date_str, align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(10)

    # ── Corps
    pdf.set_font("FreeSerif", "", 12)
    paragraphs = text.split("\n\n")

    for i, para in enumerate(paragraphs):
        lines = para.strip().split("\n")
        for j, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # Alinéa (~1 cm) sur la 1ère ligne de chaque paragraphe (sauf le 1er : "Madame, Monsieur,")
            if j == 0 and i > 0:
                pdf.cell(10)  # indent
            pdf.multi_cell(0, 7, text=line)
        pdf.ln(4)  # espace entre paragraphes

    return bytes(pdf.output())