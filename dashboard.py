import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from config import EXCLUDED_METIERS

DB_PATH = "aphp_jobs.db"

st.set_page_config(page_title="Veille APHP", page_icon="🏥", layout="wide")

CATEGORY_LABELS = {
    "metier_exclu":        "Hors métier / contrat ciblé",
    "diplome_paramedical": "Diplôme paramédical requis",
    "surqualification":    "Surqualification / poste non-cadre",
    "passed_filter_1":     "✅ Passe filtre IA",
    "profil_inadequat":    "Profil inadéquat",
}

@st.cache_data(ttl=30)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, date_publication, url, score,
               mots_cles_matches, raison, rejection_category,
               rejection_reason, first_seen, last_seen, status
        FROM jobs
    """, conn)
    conn.close()
    df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    df["first_seen"]       = pd.to_datetime(df["first_seen"],       errors="coerce")
    return df

try:
    df_all = load_data()
except Exception:
    st.error("Base de données introuvable. Lance `python main.py` d'abord.")
    st.stop()

df_active  = df_all[df_all["status"] == "active"]
df_removed = df_all[df_all["status"] == "removed"]
df_new     = df_active[df_active["first_seen"].dt.date == datetime.now().date()]

n_total        = len(df_active)
df_rej_metier  = df_active[df_active["rejection_category"] == "metier_exclu"]
n_apres_metier = n_total - len(df_rej_metier)
df_rej_ai      = df_active[df_active["rejection_category"].isin([
    "diplome_paramedical", "surqualification", "profil_inadequat"
])]
n_passed_ai    = len(df_active[df_active["rejection_category"] == "passed_filter_1"])
n_scored       = len(df_active[df_active["score"].notna()])

st.sidebar.title("🏥 Veille APHP")
st.sidebar.caption(f"Sync : {str(df_all['last_seen'].max())[:16]}")
page = st.sidebar.radio("Navigation", [
    "📊 Tableau de bord",
    "🔍 Explorer les offres",
    "✅ Offres acceptées par l'IA",
    "🆕 Nouvelles offres",
    "🗑️ Offres retirées du site",
    "⚙️  Config",
])

if page == "📊 Tableau de bord":
    st.title("📊 Tableau de bord")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total APHP",           f"{n_total:,}")
    col2.metric("Après filtre métier",  f"{n_apres_metier:,}", f"-{len(df_rej_metier)}")
    col3.metric("Après filtre IA",      f"{n_passed_ai:,}",    f"-{len(df_rej_ai)}")
    col4.metric("Score profil complet", f"{n_scored:,}",        "À venir" if n_scored == 0 else None)

    st.divider()

    tab1, tab2 = st.tabs([
        f"❌ Rejetées filtre métier/contrat ({len(df_rej_metier)})",
        f"🤖 Rejetées filtre IA ({len(df_rej_ai)})",
    ])

    with tab1:
        if df_rej_metier.empty:
            st.info("Lance `python main.py` pour appliquer les filtres.")
        else:
            df_m = df_rej_metier[["title","metier","contrat","filiere","hopital","location","rejection_reason","url"]].copy()
            df_m.columns = ["Titre","Métier","Contrat","Filière","Hôpital","Lieu","Raison","URL"]
            st.dataframe(df_m, use_container_width=True, hide_index=True,
                column_config={
                    "URL":   st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Titre": st.column_config.TextColumn(width="large"),
                })

    with tab2:
        if df_rej_ai.empty:
            st.info("Lance `python filter_ai.py` pour appliquer le filtre IA.")
        else:
            df_ai = df_rej_ai[["title","metier","filiere","rejection_category","rejection_reason","url"]].copy()
            df_ai["rejection_category"] = df_ai["rejection_category"].map(CATEGORY_LABELS)
            df_ai.columns = ["Offre","Métier","Filière","Raison simplifiée","Raison complète (IA)","URL"]
            st.dataframe(df_ai, use_container_width=True, hide_index=True,
                column_config={
                    "URL":                  st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Offre":                st.column_config.TextColumn(width="large"),
                    "Raison complète (IA)": st.column_config.TextColumn(width="large"),
                })

elif page == "🔍 Explorer les offres":
    st.title("🔍 Explorer les offres")

    with st.expander("Filtres", expanded=True):
        col1, col2, col3 = st.columns(3)
        search      = col1.text_input("Recherche titre", "")
        filiere_sel = col2.selectbox("Filière", ["Toutes"] + sorted(df_active["filiere"].dropna().unique().tolist()))
        contrat_sel = col3.selectbox("Contrat", ["Tous"]   + sorted(df_active["contrat"].dropna().unique().tolist()))
        col4, col5  = st.columns(2)
        exclure     = col4.checkbox("Appliquer filtre métiers/contrats", value=True)
        only_passed = col5.checkbox("Uniquement offres passant le filtre IA", value=False)

    df_view = df_active.copy()
    if exclure:
        df_view = df_view[df_view["rejection_category"] != "metier_exclu"]
    if search:
        df_view = df_view[df_view["title"].str.contains(search, case=False, na=False)]
    if filiere_sel != "Toutes":
        df_view = df_view[df_view["filiere"] == filiere_sel]
    if contrat_sel != "Tous":
        df_view = df_view[df_view["contrat"] == contrat_sel]
    if only_passed:
        df_view = df_view[df_view["rejection_category"] == "passed_filter_1"]

    df_view = df_view.sort_values("date_publication", ascending=False)
    st.caption(f"{len(df_view)} offres")

    df_d = df_view[["title","metier","filiere","hopital","location","contrat","teletravail","date_publication","url"]].copy()
    df_d.columns = ["Titre","Métier","Filière","Hôpital","Lieu","Contrat","Télétravail","Date","URL"]
    st.dataframe(df_d, use_container_width=True, hide_index=True,
        column_config={
            "URL":   st.column_config.LinkColumn("Lien", display_text="Voir →"),
            "Titre": st.column_config.TextColumn(width="large"),
        })

    st.divider()
    selected = st.selectbox("Détail d'une offre", ["–"] + df_view["title"].tolist())
    if selected != "–":
        row = df_view[df_view["title"] == selected].iloc[0]
        st.markdown(f"### {row['title']}")
        st.markdown(f"**🏥 {row['hopital']}** · 📍 {row['location']} · {row['contrat']}")
        st.link_button("Voir l'offre →", row["url"])

elif page == "🆕 Nouvelles offres":
    st.title("🆕 Nouvelles offres")
    df_nf = df_new[df_new["rejection_category"] != "metier_exclu"]
    st.caption(f"{len(df_nf)} nouvelles offres aujourd'hui")
    if df_nf.empty:
        st.info("Aucune nouvelle offre aujourd'hui.")
    else:
        for _, row in df_nf.iterrows():
            with st.expander(f"🆕 {row['title']} — {row['hopital']}"):
                st.markdown(f"**Métier :** {row['metier']} | **Lieu :** {row['location']} | **Contrat :** {row['contrat']}")
                st.link_button("Voir l'offre →", row["url"])

elif page == "🗑️ Offres retirées du site":
    st.title("🗑️ Offres retirées du site")
    if df_removed.empty:
        st.info("Aucune offre retirée.")
    else:
        st.caption(f"{len(df_removed)} offres retirées")
        df_r = df_removed[["title","metier","hopital","contrat","last_seen"]].copy()
        df_r.columns = ["Titre","Métier","Hôpital","Contrat","Dernière vue"]
        st.dataframe(df_r, use_container_width=True, hide_index=True)

elif page == "⚙️  Config":
    st.title("⚙️ Configuration")
    st.subheader("Métiers exclus")
    for m in EXCLUDED_METIERS:
        st.markdown(f"- ~~{m}~~")
    st.divider()
    st.subheader("Distribution des métiers")
    met = df_active["metier"].value_counts().reset_index()
    met.columns = ["Métier","Offres"]
    met["Exclu ?"] = met["Métier"].apply(lambda x: "✅" if x in EXCLUDED_METIERS else "–")
    st.dataframe(met, use_container_width=True, hide_index=True)
    st.divider()
    st.subheader("Distribution des filières")
    fil = df_active["filiere"].value_counts().reset_index()
    fil.columns = ["Filière","Offres"]
    st.dataframe(fil, use_container_width=True, hide_index=True)


elif page == "✅ Offres acceptées par l'IA":
    st.title("✅ Offres acceptées par le filtre IA")

    df_passed = df_active[df_active["rejection_category"] == "passed_filter_1"]

    if df_passed.empty:
        st.info("Lance `python filter_ai.py` pour analyser les offres.")
    else:
        st.caption(f"{len(df_passed)} offres acceptées")

        df_p = df_passed[["title", "metier", "filiere", "hopital", "location",
                           "contrat", "rejection_reason", "url"]].copy()
        df_p.columns = ["Titre", "Métier", "Filière", "Hôpital", "Lieu",
                        "Contrat", "Raison (IA)", "URL"]
        st.dataframe(df_p, use_container_width=True, hide_index=True,
            column_config={
                "URL":        st.column_config.LinkColumn("Lien", display_text="Voir →"),
                "Titre":      st.column_config.TextColumn(width="large"),
                "Raison (IA)": st.column_config.TextColumn(width="large"),
            })