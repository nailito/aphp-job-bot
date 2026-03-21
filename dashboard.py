import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from config import EXCLUDED_METIERS

DB_PATH = "aphp_jobs.db"

st.set_page_config(
    page_title="Veille APHP",
    page_icon="🏥",
    layout="wide",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid #e9ecef;
    text-align: center;
}
.metric-num  { font-size: 32px; font-weight: 600; color: #1a1a2e; }
.metric-sub  { font-size: 13px; color: #6c757d; margin-top: 4px; }
.metric-diff { font-size: 12px; margin-top: 6px; }
.new-badge  { background:#dbeafe; color:#1d4ed8; padding:2px 8px;
               border-radius:10px; font-size:11px; font-weight:500; }
.gone-badge { background:#fee2e2; color:#dc2626; padding:2px 8px;
               border-radius:10px; font-size:11px; font-weight:500; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, horaire, temps_travail,
               date_publication, url, score, mots_cles_matches,
               raison, first_seen, last_seen, status
        FROM jobs
    """, conn)
    conn.close()
    df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    df["first_seen"]       = pd.to_datetime(df["first_seen"],       errors="coerce")
    return df

def score_badge(score):
    if score is None or pd.isna(score):
        return "–"
    score = int(score)
    if score >= 70:
        return f"🟢 {score}"
    if score >= 50:
        return f"🟡 {score}"
    return f"🔴 {score}"

# ── Load ───────────────────────────────────────────────────────────────────────
try:
    df_all = load_data()
except Exception:
    st.error("Base de données introuvable. Lance `python main.py` d'abord.")
    st.stop()

today = datetime.now().date()
df_active  = df_all[df_all["status"] == "active"]
df_removed = df_all[df_all["status"] == "removed"]
df_new     = df_active[df_active["first_seen"].dt.date == today]

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("🏥 Veille APHP")
st.sidebar.caption(f"Dernière sync : {df_all['last_seen'].max()[:16] if not df_all.empty else '–'}")

page = st.sidebar.radio("Navigation", [
    "📊 Tableau de bord",
    "🔍 Explorer les offres",
    "🆕 Nouvelles offres",
    "🗑️ Offres retirées",
    "⚙️  Filtres & Config",
])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Tableau de bord":
    st.title("📊 Tableau de bord")

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-num'>{len(df_active):,}</div>
            <div class='metric-sub'>Offres actives</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        df_filtered = df_active[~df_active["metier"].isin(EXCLUDED_METIERS)]
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-num'>{len(df_filtered):,}</div>
            <div class='metric-sub'>Après filtre métier</div>
            <div class='metric-diff'>–{len(df_active) - len(df_filtered)} exclus</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        n_scored = df_active[df_active["score"].notna()]
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-num'>{len(n_scored):,}</div>
            <div class='metric-sub'>Offres scorées</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-num'>{len(df_new):,}</div>
            <div class='metric-sub'>Nouvelles aujourd'hui</div>
            <div class='metric-diff'><span class='new-badge'>NEW</span></div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # Entonnoir
    st.subheader("Entonnoir de filtrage")
    df_scored_good = n_scored[n_scored["score"] >= 70]
    funnel_data = pd.DataFrame({
        "Étape":  ["1. Total APHP", "2. Filtre métier", "3. Scorées", "4. Score ≥ 70"],
        "Offres": [len(df_active), len(df_filtered), len(n_scored), len(df_scored_good)],
    })
    st.bar_chart(funnel_data.set_index("Étape"))

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Top filières (offres actives)")
        top_fil = df_active["filiere"].value_counts().head(10).reset_index()
        top_fil.columns = ["Filière", "Offres"]
        st.dataframe(top_fil, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Top métiers (offres actives)")
        top_met = df_active["metier"].value_counts().head(10).reset_index()
        top_met.columns = ["Métier", "Offres"]
        st.dataframe(top_met, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — EXPLORER LES OFFRES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Explorer les offres":
    st.title("🔍 Explorer les offres")

    # Filtres
    with st.expander("Filtres", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            search = st.text_input("Recherche (titre / description)", "")
        with col2:
            filieres = ["Toutes"] + sorted(df_active["filiere"].dropna().unique().tolist())
            filiere_sel = st.selectbox("Filière", filieres)
        with col3:
            contrats = ["Tous"] + sorted(df_active["contrat"].dropna().unique().tolist())
            contrat_sel = st.selectbox("Contrat", contrats)

        col4, col5 = st.columns(2)
        with col4:
            exclure_metiers = st.checkbox("Appliquer filtre métiers (config.py)", value=True)
        with col5:
            only_scored = st.checkbox("Uniquement les offres scorées", value=False)

    # Application des filtres
    df_view = df_active.copy()

    if exclure_metiers:
        df_view = df_view[~df_view["metier"].isin(EXCLUDED_METIERS)]
    if search:
        mask = (
            df_view["title"].str.contains(search, case=False, na=False) |
            df_view["description"].str.contains(search, case=False, na=False)
        )
        df_view = df_view[mask]
    if filiere_sel != "Toutes":
        df_view = df_view[df_view["filiere"] == filiere_sel]
    if contrat_sel != "Tous":
        df_view = df_view[df_view["contrat"] == contrat_sel]
    if only_scored:
        df_view = df_view[df_view["score"].notna()]

    df_view = df_view.sort_values("date_publication", ascending=False)

    st.caption(f"{len(df_view)} offres affichées")

    # Tableau
    cols_display = ["title", "metier", "filiere", "hopital", "location",
                    "contrat", "teletravail", "score", "date_publication", "url"]
    df_display = df_view[cols_display].copy()
    df_display["score"] = df_display["score"].apply(
        lambda x: score_badge(x) if pd.notna(x) else "–"
    )
    df_display.columns = ["Titre", "Métier", "Filière", "Hôpital", "Lieu",
                           "Contrat", "Télétravail", "Score", "Date pub.", "URL"]

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Lien", display_text="Voir →"),
            "Titre": st.column_config.TextColumn(width="large"),
        }
    )

    # Détail d'une offre
    st.divider()
    st.subheader("Détail d'une offre")
    selected_title = st.selectbox(
        "Sélectionne une offre",
        ["–"] + df_view["title"].tolist()
    )
    if selected_title != "–":
        row = df_view[df_view["title"] == selected_title].iloc[0]
        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.markdown(f"### {row['title']}")
            st.markdown(f"**🏥 {row['hopital']}** · 📍 {row['location']}")
            st.markdown(f"**Contrat :** {row['contrat']} | **Télétravail :** {row['teletravail']}")
            if pd.notna(row.get("score")):
                st.markdown(f"**Score :** {score_badge(row['score'])}/100")
                st.markdown(f"**Mots-clés :** {row.get('mots_cles_matches','–')}")
                st.markdown(f"**Analyse :** {row.get('raison','–')}")
            st.link_button("Voir l'offre sur aphp.fr →", row["url"])
        with col_b:
            st.markdown("**Description**")
            st.text_area("", row.get("description", ""), height=300, label_visibility="collapsed")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — NOUVELLES OFFRES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🆕 Nouvelles offres":
    st.title("🆕 Nouvelles offres")

    if df_new.empty:
        st.info("Aucune nouvelle offre aujourd'hui. Relance `python main.py` pour synchroniser.")
    else:
        df_new_filtered = df_new[~df_new["metier"].isin(EXCLUDED_METIERS)]
        st.caption(f"{len(df_new_filtered)} nouvelles offres aujourd'hui (après filtre métier)")

        for _, row in df_new_filtered.iterrows():
            with st.expander(f"🆕 {row['title']} — {row['hopital']}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Métier :** {row['metier']} | **Filière :** {row['filiere']}")
                    st.markdown(f"**Lieu :** {row['location']} | **Contrat :** {row['contrat']}")
                    st.link_button("Voir l'offre →", row["url"])
                with col2:
                    if pd.notna(row.get("score")):
                        st.metric("Score", f"{int(row['score'])}/100")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — OFFRES RETIRÉES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗑️ Offres retirées":
    st.title("🗑️ Offres retirées du site")

    if df_removed.empty:
        st.info("Aucune offre retirée enregistrée.")
    else:
        st.caption(f"{len(df_removed)} offres retirées au total")
        df_rem_display = df_removed[["title", "metier", "hopital", "contrat", "last_seen"]].copy()
        df_rem_display.columns = ["Titre", "Métier", "Hôpital", "Contrat", "Dernière vue"]
        st.dataframe(df_rem_display, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — CONFIG
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️  Filtres & Config":
    st.title("⚙️ Filtres & Configuration")

    st.subheader("Métiers exclus (config.py)")
    st.caption("Ces métiers sont filtrés avant le scoring IA.")
    for m in EXCLUDED_METIERS:
        st.markdown(f"- ~~{m}~~")

    st.divider()
    st.subheader("Distribution des métiers (offres actives)")
    st.caption("Utilise ce tableau pour identifier les métiers à ajouter dans EXCLUDED_METIERS.")
    met_count = df_active["metier"].value_counts().reset_index()
    met_count.columns = ["Métier", "Offres"]
    met_count["Exclu ?"] = met_count["Métier"].apply(
        lambda x: "✅ Exclu" if x in EXCLUDED_METIERS else "–"
    )
    st.dataframe(met_count, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Distribution des filières")
    fil_count = df_active["filiere"].value_counts().reset_index()
    fil_count.columns = ["Filière", "Offres"]
    st.dataframe(fil_count, use_container_width=True, hide_index=True)