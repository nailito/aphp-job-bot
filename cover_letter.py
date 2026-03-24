def generate_cover_letter(job_title: str, job_description: str, hopital: str, cv_text: str) -> str:
    """Génère une lettre de motivation adaptée à l'offre, en 3 paragraphes, style Naïl."""
    client = Groq(api_key=GROQ_API_KEY)

    # ── Few-shot : LM réelle de Naïl comme référence de style et de longueur
    EXAMPLE_JOB = """
Titre : Ingénieur de recherche — projet RAISE-AKI
Hôpital : Hôpital Européen Georges-Pompidou
Description : Développement d'un modèle prédictif d'insuffisance rénale aiguë (AKI) à partir
des données du SIH. Contribution à la librairie open-source aircohort. Encadrement d'étudiants
en médecine. Stack : Python, Docker, CI/CD.
"""

    EXAMPLE_LM = """Madame, Monsieur,

Déjà confronté à la complexité des données hospitalières lors de mon passage au Slagelse Hospital, je mesure l'impact qu'un modèle fiable de prédiction de l'insuffisance rénale aiguë peut avoir sur la prise en charge des patients et la fluidité des blocs opératoires. C'est pourquoi le projet RAISE-AKI et le poste d'ingénieur de recherche au sein du service d'informatique biomédicale de l'Hôpital Européen Georges-Pompidou me stimulent : ils offrent l'opportunité de transformer des données brutes en outils cliniques tangibles, tout en participant à l'enrichissement de la librairie aircohort.

Ma maîtrise de Python (Pandas, Scikit-learn) et SQL m'a permis de nettoyer et de modéliser des millions de lignes issues des SIH danois, réduisant de 20 % les retards de bloc et de 15 % l'inactivité des salles. Parallèlement, j'ai encadré des étudiants en master sur des projets d'optimisation stochastique, expérience que je souhaite mettre au service des étudiants en médecine que je coacherai sur RAISE-AKI. Mon approche industrialisée (Docker, CI/CD) garantira des pipelines reproductibles, pilier de la librairie aircohort.

Rejoindre l'APHP, côtoyer la plus grande masse de données de santé francophone et collaborer avec des équipes pluridisciplinaires d'excellence, c'est aussi contribuer à une politique de soins qui touche chaque jour des millions de patients. Je suis disponible immédiatement pour échanger sur la faisabilité technique des modèles et sur la façon dont mes expériences européennes peuvent accélérer le calendrier du projet.

Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

Naïl Mulatier"""

    prompt = f"""Tu es Naïl Mulatier. Tu dois rédiger une lettre de motivation pour une offre à l'APHP.

RÈGLES ABSOLUES :
- Exactement 3 paragraphes de corps (hors formule d'appel et formule de politesse)
- Longueur identique à l'exemple ci-dessous : ~4-5 phrases par paragraphe, ni plus ni moins
- Ton professionnel mais humain, phrases construites — pas de bullet points, pas de titres
- Ne jamais inventer de compétences ou expériences absentes du CV
- Chaque paragraphe doit avoir un rôle distinct, choisi librement selon ce qui est le plus pertinent pour l'offre
- Commencer par "Madame, Monsieur,"
- Terminer par "Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n\nNaïl Mulatier"

EXEMPLE DE RÉFÉRENCE (style, longueur, ton à reproduire) :
Offre : {EXAMPLE_JOB}
Lettre : {EXAMPLE_LM}

---

MAINTENANT, génère la lettre pour cette offre :

Titre : {job_title}
Hôpital : {hopital}
Description : {job_description[:1500]}

CV DE NAÏL :
{cv_text}

Génère uniquement la lettre, sans commentaire ni balise."""

    response = client.chat.completions.create(
        model="moonshotai/kimi-k2-instruct-0905",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()