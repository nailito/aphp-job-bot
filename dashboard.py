import streamlit as st
import psycopg2
import os
import pandas as pd
from datetime import datetime
from config import EXCLUDED_METIERS
from cover_letter import text_to_pdf

DATABASE_URL = os.getenv("DATABASE_URL", "")

st.set_page_config(page_title="Veille APHP", page_icon="🏥", layout="wide")

CATEGORY_LABELS = {
    "metier_exclu":        "Hors métier / contrat ciblé",
    "diplome_paramedical": "Diplôme paramédical requis",
    "surqualification":    "Surqualification / poste non-cadre",
    "passed_filter_1":     "✅ Passe filtre IA",
    "profil_inadequat":    "Profil inadéquat",
}

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

@st.cache_data(ttl=30)
def load_data():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, date_publication, url, score,
               priorite, score_raison, score_points_forts, score_points_faibles,
               mots_cles_matches, raison, rejection_category, description,
               rejection_reason, first_seen, last_seen, status
        FROM jobs
    """, conn)
    conn.close()
    df = df.drop_duplicates(subset="id")
    df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    df["first_seen"]       = pd.to_datetime(df["first_seen"],       errors="coerce")
    return df

try:
    df_all = load_data()
except Exception as e:
    st.error(f"Erreur de connexion à la base de données : {e}")
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
n_a_trier      = len(df_active[df_active["rejection_category"] == "a_trier"])

st.sidebar.title("🏥 Veille APHP")
st.sidebar.caption(f"Sync : {str(df_all['last_seen'].max())[:16]}")

pages = [
    "📊 Tableau de bord",
    "🚀 À postuler",
    "📰 Rapport du jour",
    "🔍 Explorer les offres",
    "✅ Offres acceptées par l'IA",
    "❌ Offres refusées par score",
    "📝 À évaluer",
    "🆕 Nouvelles offres",
    "🗑️ Offres retirées du site",
    "⚙️  Config",
]

page = st.sidebar.radio(
    "Navigation",
    pages,
    index=pages.index(st.session_state.get("nav", "📊 Tableau de bord"))
)

# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Tableau de bord":
    st.title("📊 Tableau de bord")

    # ── Bandeau dernière actualisation
    conn = get_connection()
    runs = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY run_date DESC LIMIT 1", conn)
    conn.close()

    if not runs.empty:
        last = runs.iloc[0]
        run_date_str = last["run_date"][:16].replace("T", " ")
        date_fmt = run_date_str[:10].replace("-", "/")
        heure_fmt = run_date_str[11:16].replace(":", "h")
        is_success = str(last["status"]).startswith("success") or last["status"] == "no_new_offers"
        emoji = "✅" if is_success else "❌"
        st.info(f"{emoji} Dernière actualisation le **{date_fmt}** à **{heure_fmt}** — statut : `{last['status']}`")
    else:
        st.warning("⚠️ Aucun pipeline exécuté pour l'instant.")

    st.divider()

    # ── Meilleure offre évaluée
    from database import get_feedbacks
    feedbacks = get_feedbacks()
    feedbacks_positifs = {f["job_id"] for f in feedbacks if f["decision"] in ["⭐", "👍"]}

    df_top = df_active[
        (df_active["id"].isin(feedbacks_positifs)) &
        (df_active["score"].notna())
    ].copy()

    if not df_top.empty:
        df_top["score_num"] = pd.to_numeric(df_top["score"], errors="coerce")
        best = df_top.sort_values("score_num", ascending=False).iloc[0]

        st.markdown("### 🏆 Meilleure offre évaluée")
        col_card, col_btn = st.columns([4, 1])
        with col_card:
            score_val = int(best["score"]) if pd.notna(best["score"]) else "–"
            prio = best.get("priorite", "–")
            st.markdown(f"""
            <div style="
                background:#f0f9ff;
                border-left:4px solid #6366f1;
                padding:16px;
                border-radius:8px;
                color:#111;
            ">
                <div style="font-size:1.2rem;font-weight:700;color:#111">
                    {best['title']}
                </div>
                <div style="color:#444;margin-top:4px">
                    🏥 {best['hopital']} · 📍 {best['location']} · 📄 {best['contrat']}
                </div>
                <div style="margin-top:8px;color:#111">
                    🎯 <b>Score : {score_val}/100</b> · Priorité : <b>{prio}</b>
                </div>
                <div style="color:#555;margin-top:6px;font-size:0.9rem">
                    {best.get('score_raison','')}
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col_btn:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.link_button("🚀 Postuler →", best["url"], use_container_width=True, type="primary")
    else:
        st.info("🏆 Aucune offre évaluée positivement pour l'instant — rendez-vous dans **📝 À évaluer**.")

    st.divider()

    # ── Compteurs offres à évaluer / à postuler
    feedbacks_existants = {f["job_id"] for f in feedbacks}
    n_a_evaluer  = len(df_active[
        (df_active["rejection_category"] == "passed_filter_1") &
        (~df_active["id"].isin(feedbacks_existants))
    ])
    n_a_postuler = len(df_active[df_active["id"].isin(feedbacks_positifs)])

    col_ev, col_pos = st.columns(2)
    if "nav" not in st.session_state:
        st.session_state.nav = "📊 Tableau de bord"

    col_ev, col_pos = st.columns(2)

    with col_ev:
        if st.button(f"📝 Offres à évaluer\n\n{n_a_evaluer}", use_container_width=True):
            st.session_state.nav = "📝 À évaluer"
            st.rerun()

    with col_pos:
        if st.button(f"🚀 Offres à postuler\n\n{n_a_postuler}", use_container_width=True):
            st.session_state.nav = "🚀 Postuler"  # future page
            st.rerun()

    st.divider()

    # ── Camembert pipeline
    import plotly.graph_objects as go

    n_total_actif   = len(df_active)
    n_rej_metier    = len(df_active[df_active["rejection_category"] == "metier_exclu"])
    n_rej_ia        = len(df_active[df_active["rejection_category"].isin([
        "diplome_paramedical", "surqualification", "profil_inadequat"
    ])])
    n_scored_val    = len(df_active[df_active["score"].notna()])
    n_passed_no_score = len(df_active[
        (df_active["rejection_category"] == "passed_filter_1") &
        (df_active["score"].isna())
    ])

    labels = [
        "❌ Filtre métier/contrat",
        "🤖 Rejeté filtre IA",
        "⏳ Passé IA (sans score)",
        "🎯 Scorées",
    ]
    values = [n_rej_metier, n_rej_ia, n_passed_no_score, n_scored_val]
    colors = ["#f87171", "#fb923c", "#a78bfa", "#34d399"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hovertemplate="%{label}<br>%{value} offres<br>%{percent}<extra></extra>",
    )])
    fig.update_layout(
        title=dict(text=f"Répartition des {n_total_actif:,} offres APHP actives", x=0.5),
        showlegend=False,
        margin=dict(t=60, b=20, l=20, r=20),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)


elif page == "🚀 À postuler":
    st.title("🚀 Offres à postuler")

    from database import get_feedbacks, get_application, save_application
    from cover_letter import select_cv_base, generate_cover_letter, adapt_cv
    import json

    feedbacks = get_feedbacks()
    feedbacks_positifs = {f["job_id"] for f in feedbacks if f["decision"] in ["⭐", "👍"]}
    df_postuler = df_active[df_active["id"].isin(feedbacks_positifs)].copy()

    if df_postuler.empty:
        st.info("Aucune offre à postuler — évalue des offres dans **📝 À évaluer**.")
        st.stop()

    df_postuler["score_num"] = pd.to_numeric(df_postuler["score"], errors="coerce")
    df_postuler = df_postuler.sort_values("score_num", ascending=False).reset_index(drop=True)

    if "selected_job_apply" not in st.session_state:
        st.session_state.selected_job_apply = df_postuler.iloc[0]["id"]

    col_left, col_right = st.columns([1, 2])

    # ── COLONNE GAUCHE — liste
    with col_left:
        st.subheader(f"📋 {len(df_postuler)} offres")
        for _, row in df_postuler.iterrows():
            job_id  = row["id"]
            score   = int(row["score"]) if pd.notna(row["score"]) else "–"
            app     = get_application(job_id)
            status  = app["status"] if app else "draft"
            status_emoji = {"draft": "📝", "ready": "✅", "applied": "🚀"}.get(status, "📝")
            decision_emoji = "⭐" if job_id in {f["job_id"] for f in feedbacks if f["decision"] == "⭐"} else "👍"
            label = f"{status_emoji} {decision_emoji} {row['title'][:35]}... ({score}/100)"
            active = job_id == st.session_state.selected_job_apply
            if st.button(label, key=f"apply_{job_id}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.selected_job_apply = job_id
                st.rerun()

    # ── COLONNE DROITE — détail
    with col_right:
        job = df_postuler[df_postuler["id"] == st.session_state.selected_job_apply].iloc[0]
        job_id = job["id"]
        app = get_application(job_id) or {}

        # ── Infos offre
        st.subheader(job["title"])
        st.markdown(f"**🏥 {job['hopital']}** · 📍 {job['location']} · 📄 {job['contrat']}")
        score = int(job["score"]) if pd.notna(job["score"]) else "–"
        col_s, col_p = st.columns(2)
        col_s.metric("Score", f"{score}/100")
        col_p.metric("Priorité", job.get("priorite", "–"))

        if pd.notna(job.get("score_raison")):
            with st.expander("🧠 Analyse IA"):
                st.write(job["score_raison"])
                try:
                    pf = json.loads(job.get("score_points_forts") or "[]")
                    pp = json.loads(job.get("score_points_faibles") or "[]")
                    if pf:
                        st.markdown("**✅ Points forts :** " + " · ".join(pf))
                    if pp:
                        st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                except Exception:
                    pass

        st.link_button("🔗 Voir l'offre APHP", job["url"])
        st.divider()

        # ══════════════════════════════════
        # 📄 LETTRE DE MOTIVATION
        # ══════════════════════════════════
        st.markdown("### 📄 Lettre de motivation")

        lm_validated = app.get("lm_validated", False)
        lm_text      = app.get("lm_text", "")

        col_gen_lm, col_valid_lm = st.columns([2, 1])

        with col_gen_lm:
            if st.button("🤖 Générer LM avec l'IA", key=f"gen_lm_{job_id}",
                         use_container_width=True, disabled=lm_validated):
                with st.spinner("Génération en cours (kimi-k2)..."):
                    try:
                        _, cv_text = select_cv_base(job["title"], str(job.get("description", "")))
                        lm = generate_cover_letter(
                            job["title"],
                            str(job.get("description", "")),
                            job["hopital"],
                            cv_text
                        )
                        save_application(job_id, lm_text=lm, lm_validated=False)
                        st.session_state[f"lm_text_{job_id}"] = lm
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur génération : {e}")

        with col_valid_lm:
            if lm_validated:
                if st.button("🔓 Modifier LM", key=f"unlock_lm_{job_id}", use_container_width=True):
                    save_application(job_id, lm_validated=False)
                    st.rerun()
            else:
                if st.button("✅ Valider LM", key=f"valid_lm_{job_id}",
                             use_container_width=True,
                             disabled=not (lm_text or st.session_state.get(f"lm_text_{job_id}"))):
                    current = st.session_state.get(f"lm_text_{job_id}", lm_text)
                    save_application(job_id, lm_text=current, lm_validated=True)
                    st.rerun()

        current_lm = st.session_state.get(f"lm_text_{job_id}", lm_text)
        if current_lm:
            edited_lm = st.text_area(
                "Lettre de motivation",
                value=current_lm,
                height=300,
                disabled=lm_validated,
                key=f"lm_area_{job_id}",
                label_visibility="collapsed"
            )
            if not lm_validated:
                st.session_state[f"lm_text_{job_id}"] = edited_lm

            from cover_letter import text_to_pdf
            pdf_bytes = text_to_pdf(current_lm, f"Lettre de motivation — {job['title']}")
            st.download_button(
                label="📥 Télécharger LM (PDF)",
                data=pdf_bytes,
                file_name=f"LM_{job_id}.pdf",
                mime="application/pdf",
                key=f"dl_lm_{job_id}"
            )
        else:
            st.caption("Clique sur **Générer LM** pour créer une lettre adaptée à cette offre.")

        st.divider()

        # ══════════════════════════════════
        # 📋 CV ADAPTÉ
        # ══════════════════════════════════
        st.markdown("### 📋 CV adapté")

        cv_validated = app.get("cv_validated", False)
        cv_text      = app.get("cv_adapted_text", "")
        cv_base_used = app.get("cv_base_used", "")

        col_gen_cv, col_valid_cv = st.columns([2, 1])

        with col_gen_cv:
            if st.button("🤖 Générer CV adapté avec l'IA", key=f"gen_cv_{job_id}",
                         use_container_width=True, disabled=cv_validated):
                with st.spinner("Sélection du CV de base + adaptation (kimi-k2)..."):
                    try:
                        base_name, base_text = select_cv_base(
                            job["title"], str(job.get("description", ""))
                        )
                        adapted = adapt_cv(
                            job["title"],
                            str(job.get("description", "")),
                            base_text
                        )
                        save_application(job_id,
                                         cv_base_used=base_name,
                                         cv_adapted_text=adapted,
                                         cv_validated=False)
                        st.session_state[f"cv_text_{job_id}"] = adapted
                        st.session_state[f"cv_base_{job_id}"] = base_name
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur génération : {e}")

        with col_valid_cv:
            if cv_validated:
                if st.button("🔓 Modifier CV", key=f"unlock_cv_{job_id}", use_container_width=True):
                    save_application(job_id, cv_validated=False)
                    st.rerun()
            else:
                if st.button("✅ Valider CV", key=f"valid_cv_{job_id}",
                             use_container_width=True,
                             disabled=not (cv_text or st.session_state.get(f"cv_text_{job_id}"))):
                    current = st.session_state.get(f"cv_text_{job_id}", cv_text)
                    save_application(job_id, cv_adapted_text=current, cv_validated=True)
                    st.rerun()

        base_display = st.session_state.get(f"cv_base_{job_id}", cv_base_used)
        if base_display:
            labels = {"data": "Analyste de données", "organisation": "Ingénieur en Organisation", "ro": "Ingénieur R.O."}
            st.caption(f"📎 CV de base sélectionné : **{labels.get(base_display, base_display)}**")

        current_cv = st.session_state.get(f"cv_text_{job_id}", cv_text)
        if current_cv:
            edited_cv = st.text_area(
                "CV adapté",
                value=current_cv,
                height=300,
                disabled=cv_validated,
                key=f"cv_area_{job_id}",
                label_visibility="collapsed"
            )
            if not cv_validated:
                st.session_state[f"cv_text_{job_id}"] = edited_cv

            from cover_letter import text_to_pdf
            pdf_bytes = text_to_pdf(current_cv, "CV — Naïl Mulatier")
            st.download_button(
                label="📥 Télécharger CV (PDF)",
                data=pdf_bytes,
                file_name=f"CV_{job_id}.pdf",
                mime="application/pdf",
                key=f"dl_cv_{job_id}"
            )
        else:
            st.caption("Clique sur **Générer CV adapté** pour obtenir un CV ciblé sur ce poste.")

        st.divider()

        # ══════════════════════════════════
        # 🚀 ACTIONS FINALES
        # ══════════════════════════════════
        both_validated = lm_validated and cv_validated
        status = app.get("status", "draft")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if status == "applied":
                st.success("🚀 Candidature envoyée !")
            else:
                if st.button(
                    "🚀 Postuler",
                    key=f"postuler_{job_id}",
                    use_container_width=True,
                    type="primary",
                    disabled=not both_validated,
                    help="Valide LM et CV avant de postuler" if not both_validated else ""
                ):
                    # Pour l'instant → ouvre le site APHP
                    st.link_button("🔗 Postuler sur APHP →", job["url"])
                    save_application(job_id, status="applied",
                                     applied_at=datetime.now().isoformat())
                    st.rerun()

        with col_b:
            if st.button("❌ Retirer", key=f"retirer_{job_id}", use_container_width=True):
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM feedback WHERE job_id = %s", (job["id"],))
                    conn.commit()
                st.success("Offre retirée.")
                st.cache_data.clear()
                st.rerun()

        with col_c:
            if both_validated and status != "applied":
                st.info("✅ Prêt à postuler !")
            elif not both_validated:
                missing = []
                if not lm_validated: missing.append("LM")
                if not cv_validated:  missing.append("CV")
                st.warning(f"En attente : {' + '.join(missing)}")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "📰 Rapport du jour":
    st.title("📰 Rapport du jour")

    conn = get_connection()
    runs = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY run_date DESC LIMIT 30", conn)
    conn.close()

    if runs.empty:
        st.info("Aucun pipeline exécuté. Lance `python pipeline.py` pour démarrer.")
    else:
        last     = runs.iloc[0]
        run_date = last["run_date"][:10]

        if last["n_new"] == 0:
            st.success(f"✅ Dernier run le {run_date} — Aucune nouvelle offre")
        else:
            st.info(f"📅 Dernier run le {run_date} — **{last['n_new']} nouvelles offres** détectées")

        st.divider()

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🌐 Scrappées",  f"{last['n_scraped']:,}")
        col2.metric("🆕 Nouvelles",  f"{last['n_new']:,}")
        col3.metric("🗑️ Retirées",   f"{last['n_removed']:,}")
        col4.metric("✅ Passées IA", f"{last['n_passed_ai']:,}")
        col5.metric("🎯 Scorées",    f"{last['n_scored']:,}")

        st.divider()

        df_nouvelles = df_active[
            df_active["first_seen"].dt.date == pd.Timestamp(last["run_date"][:10]).date()
        ].copy()

        if not df_nouvelles.empty:
            tab1, tab2, tab3 = st.tabs([
                f"✅ Passées IA ({len(df_nouvelles[df_nouvelles['rejection_category'] == 'passed_filter_1'])})",
                f"❌ Rejetées ({len(df_nouvelles[df_nouvelles['rejection_category'].isin(['metier_exclu','diplome_paramedical','surqualification'])])})",
                f"🎯 Scorées ({len(df_nouvelles[df_nouvelles['score'].notna()])})",
            ])

            with tab1:
                df_p = df_nouvelles[df_nouvelles["rejection_category"] == "passed_filter_1"]
                if df_p.empty:
                    st.info("Aucune offre passée le filtre IA.")
                else:
                    df_p = df_p[["title","metier","hopital","location","contrat","score","url"]].copy()
                    df_p.columns = ["Titre","Métier","Hôpital","Lieu","Contrat","Score","URL"]
                    st.dataframe(df_p, use_container_width=True, hide_index=True,
                        column_config={"URL": st.column_config.LinkColumn("Lien", display_text="Voir →"),
                                       "Titre": st.column_config.TextColumn(width="large")})

            with tab2:
                df_r = df_nouvelles[df_nouvelles["rejection_category"].isin(
                    ["metier_exclu","diplome_paramedical","surqualification","profil_inadequat"]
                )]
                if df_r.empty:
                    st.info("Aucune offre rejetée.")
                else:
                    df_r = df_r[["title","metier","rejection_category","rejection_reason","url"]].copy()
                    df_r["rejection_category"] = df_r["rejection_category"].map(CATEGORY_LABELS)
                    df_r.columns = ["Titre","Métier","Catégorie","Raison","URL"]
                    st.dataframe(df_r, use_container_width=True, hide_index=True,
                        column_config={"URL": st.column_config.LinkColumn("Lien", display_text="Voir →"),
                                       "Titre": st.column_config.TextColumn(width="large")})

            with tab3:
                df_s = df_nouvelles[df_nouvelles["score"].notna()].sort_values("score", ascending=False)
                if df_s.empty:
                    st.info("Aucune offre scorée.")
                else:
                    df_s = df_s[["score","priorite","title","metier","hopital","score_raison","url"]].copy()
                    df_s.columns = ["Score","Priorité","Titre","Métier","Hôpital","Analyse","URL"]
                    st.dataframe(df_s, use_container_width=True, hide_index=True,
                        column_config={"URL": st.column_config.LinkColumn("Lien", display_text="Voir →"),
                                       "Titre": st.column_config.TextColumn(width="large"),
                                       "Score": st.column_config.NumberColumn(format="%d/100")})

        st.divider()
        st.subheader("📈 Historique des runs")
        runs_display = runs[["run_date","n_new","n_removed","n_passed_ai","n_scored","status","duration_sec"]].copy()
        runs_display["run_date"]     = runs_display["run_date"].str[:16]
        runs_display["duration_sec"] = runs_display["duration_sec"].apply(lambda x: f"{x}s")
        runs_display.columns = ["Date","Nouvelles","Retirées","Passées IA","Scorées","Statut","Durée"]
        st.dataframe(runs_display, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("🚀 Lancer le pipeline manuellement")
    if st.button("▶️ Lancer le pipeline maintenant", use_container_width=True, type="primary"):
        with st.spinner("Pipeline en cours... (peut prendre plusieurs minutes)"):
            import subprocess
            result = subprocess.run(["python", "pipeline.py"], capture_output=True, text=True)
            if result.returncode == 0:
                st.success("✅ Pipeline terminé !")
                st.code(result.stdout[-2000:])
            else:
                st.error("❌ Erreur pipeline")
                st.code(result.stderr[-2000:])
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
elif page == "✅ Offres acceptées par l'IA":
    st.title("✅ Offres acceptées par le filtre IA")

    df_passed = df_active[df_active["rejection_category"] == "passed_filter_1"].copy()

    if df_passed.empty:
        st.info("Lance `python filter_ai.py` pour analyser les offres.")
    else:
        df_scorees     = df_passed[df_passed["score"].notna()].sort_values("score", ascending=False)
        df_non_scorees = df_passed[df_passed["score"].isna()]

        st.caption(f"{len(df_passed)} offres acceptées — {len(df_scorees)} scorées, {len(df_non_scorees)} en attente")

        tab_scorees, tab_non_scorees = st.tabs([
            f"🎯 Scorées ({len(df_scorees)})",
            f"⏳ En attente de score ({len(df_non_scorees)})",
        ])

        with tab_scorees:
            df_s = df_scorees[["score","priorite","title","metier","filiere",
                                "hopital","location","contrat","score_raison","url"]].copy()
            df_s.columns = ["Score","Priorité","Titre","Métier","Filière",
                            "Hôpital","Lieu","Contrat","Analyse IA","URL"]
            st.dataframe(df_s, use_container_width=True, hide_index=True,
                column_config={
                    "URL":        st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Titre":      st.column_config.TextColumn(width="large"),
                    "Analyse IA": st.column_config.TextColumn(width="large"),
                    "Score":      st.column_config.NumberColumn(format="%d/100"),
                })

        with tab_non_scorees:
            df_ns = df_non_scorees[["title","metier","filiere","hopital","location","contrat","url"]].copy()
            df_ns.columns = ["Titre","Métier","Filière","Hôpital","Lieu","Contrat","URL"]
            st.dataframe(df_ns, use_container_width=True, hide_index=True,
                column_config={
                    "URL":   st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Titre": st.column_config.TextColumn(width="large"),
                })
            st.info("Lance `python -c \"from scorer import run_scorer; run_scorer()\"` pour scorer.")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "❌ Offres refusées par score":
    st.title("❌ Offres refusées par score IA")

    df_refuses = df_active[
        (df_active["rejection_category"] == "profil_inadequat") &
        (df_active["score"].notna())
    ].copy().drop_duplicates(subset="id")

    if df_refuses.empty:
        st.info("Aucune offre refusée par score pour l'instant.")
    else:
        df_refuses["score_num"] = pd.to_numeric(df_refuses["score"], errors="coerce")
        df_refuses = df_refuses.sort_values("score_num", ascending=False).reset_index(drop=True)
        st.caption(f"{len(df_refuses)} offres refusées (score < 50)")

        for idx, row in df_refuses.iterrows():
            job_key = f"{idx}_{row['id']}"
            score   = int(row["score"]) if pd.notna(row.get("score")) else 0

            with st.expander(f"🔴 {score}/100 — **{row['title']}** — {row['hopital']}"):
                st.markdown(f"**Métier :** {row['metier']} | **Filière :** {row['filiere']}")
                st.markdown(f"**📍 {row['location']}** | **📄 {row['contrat']}** | **🖥 {row['teletravail']}**")
                st.link_button("Voir l'offre →", row["url"])

                st.divider()
                col_score, col_prio = st.columns(2)
                col_score.metric("Score", f"{score}/100")
                col_prio.metric("Priorité", row.get("priorite", "–"))
                st.markdown(f"**Raison du refus :** {row.get('score_raison', '–')}")

                if pd.notna(row.get("score_points_faibles")):
                    try:
                        import json
                        pf = json.loads(row["score_points_faibles"])
                        if pf:
                            st.markdown("**Points faibles :**")
                            for p in pf:
                                st.markdown(f"- ⚠️ {p}")
                    except Exception:
                        pass

                st.divider()
                if st.button("🔄 Remettre en question cette évaluation", key=f"reeval_{job_key}", use_container_width=True):
                    with get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE jobs
                                SET rejection_category = 'passed_filter_1',
                                    score = NULL, priorite = NULL,
                                    score_raison = NULL,
                                    score_points_forts = NULL,
                                    score_points_faibles = NULL
                                WHERE id = %s
                            """, (row["id"],))
                        conn.commit()
                    st.success("✅ Offre remise dans la liste à évaluer !")
                    st.cache_data.clear()
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
elif page == "📝 À évaluer":
    st.title("📝 À évaluer")

    from database import save_feedback, get_feedbacks, delete_feedback

    feedbacks_existants = {f["job_id"] for f in get_feedbacks()}
    df_a_evaluer = df_active[
        (df_active["rejection_category"] == "passed_filter_1") &
        (~df_active["id"].isin(feedbacks_existants))
    ].copy().drop_duplicates(subset="id")

    df_deja_evalues = df_active[df_active["id"].isin(feedbacks_existants)].copy()

    tab_eval, tab_done = st.tabs([
        f"⏳ À évaluer ({len(df_a_evaluer)})",
        f"✅ Déjà évalués ({len(df_deja_evalues)})",
    ])

    with tab_eval:
        if df_a_evaluer.empty:
            st.info("Toutes les offres ont été évaluées ! 🎉")
        else:
            col_tri, _ = st.columns([1, 3])
            tri = col_tri.selectbox(
                "Trier par",
                ["Score (meilleur en premier)", "Score (moins bon en premier)", "Date de publication"],
                key="tri_eval"
            )

            df_a_evaluer["score_num"] = pd.to_numeric(df_a_evaluer["score"], errors="coerce")

            if tri == "Score (meilleur en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=False, na_position="last").reset_index(drop=True)
            elif tri == "Score (moins bon en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=True, na_position="last").reset_index(drop=True)
            else:
                df_a_evaluer = df_a_evaluer.sort_values("date_publication", ascending=False).reset_index(drop=True)

            for idx, row in df_a_evaluer.iterrows():
                score_label = f"🎯 {int(row['score'])}/100 — " if pd.notna(row.get("score")) else ""
                prio_label  = f"[{row['priorite']}] " if pd.notna(row.get("priorite")) else ""
                job_id      = row["id"]
                job_key     = f"{idx}_{job_id}"

                with st.expander(f"{score_label}{prio_label}**{row['title']}** — {row['hopital']}"):
                    st.markdown(f"**Métier :** {row['metier']} | **Filière :** {row['filiere']}")
                    st.markdown(f"**📍 {row['location']}** | **📄 {row['contrat']}** | **🖥 {row['teletravail']}**")

                    date_pub = row["date_publication"].strftime("%d/%m/%Y") if pd.notna(row.get("date_publication")) else "–"
                    st.markdown(f"**📅 Publiée le :** {date_pub}")
                    st.link_button("Voir l'offre →", row["url"])

                    if st.button("✨ Générer résumé", key=f"resume_{job_key}"):
                        with st.spinner("Génération en cours..."):
                            try:
                                from groq import Groq
                                from config import GROQ_API_KEY
                                client = Groq(api_key=GROQ_API_KEY)
                                response = client.chat.completions.create(
                                    model="llama-3.1-8b-instant",
                                    max_tokens=200,
                                    messages=[{"role": "user", "content": f"""
Résume cette offre d'emploi en 3 bullet points courts (max 15 mots chacun).
Focus sur : le rôle principal, les compétences clés demandées, le contexte/service.
Réponds directement sans introduction.

Titre : {row['title']}
Description : {str(row.get('description', ''))[:1500]}
"""}]
                                )
                                st.session_state[f"resume_text_{job_id}"] = response.choices[0].message.content.strip()
                            except Exception as e:
                                st.error(f"Erreur : {e}")

                    if f"resume_text_{job_id}" in st.session_state:
                        st.markdown(st.session_state[f"resume_text_{job_id}"])

                    if pd.notna(row.get("score")):
                        col_score, col_prio = st.columns(2)
                        col_score.metric("Score", f"{int(row['score'])}/100")
                        col_prio.metric("Priorité", row.get("priorite", "–"))
                        st.markdown(f"**Analyse IA :** {row.get('score_raison', '–')}")

                    st.divider()

                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        btn_top = st.button("⭐ Excellent",        key=f"top_{job_key}", use_container_width=True)
                    with col_b:
                        btn_oui = st.button("👍 Intéressant",      key=f"oui_{job_key}", use_container_width=True)
                    with col_c:
                        btn_non = st.button("👎 Pas intéressant",  key=f"non_{job_key}", use_container_width=True)

                    if btn_top: st.session_state[f"dec_{job_id}"] = "⭐"
                    if btn_oui: st.session_state[f"dec_{job_id}"] = "👍"
                    if btn_non: st.session_state[f"dec_{job_id}"] = "👎"

                    if f"dec_{job_id}" in st.session_state:
                        dec = st.session_state[f"dec_{job_id}"]
                        st.markdown(f"**Décision : {dec}**")
                        commentaire = st.text_area(
                            "Ton feedback :",
                            key=f"comment_{job_key}",
                            placeholder="Ex: Très bon poste, SQL + Python demandés...",
                            height=80,
                        )
                        if st.button("💾 Sauvegarder", key=f"save_{job_key}", use_container_width=True):
                            save_feedback(job_id, dec, [], commentaire)
                            st.success("✅ Sauvegardé !")
                            st.cache_data.clear()
                            st.rerun()

    with tab_done:
        if df_deja_evalues.empty:
            st.info("Aucun feedback encore.")
        else:
            # On joint avec feedbacks pour récupérer decision/commentaire
            feedback_map = {f["job_id"]: f for f in get_feedbacks()}

            for _, row in df_deja_evalues.iterrows():
                f = feedback_map.get(row["id"], {})

                with st.expander(f"{f.get('decision','?')} **{row['title']}** — {row['hopital']}"):
                    st.markdown(f"**Feedback :** {f.get('commentaire','–')}")
                    st.markdown(f"**Date :** {f.get('created_at','')[:10]}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.link_button("Voir l'offre →", row["url"])
                    with col2:
                        if st.button("🗑️ Supprimer", key=f"del_{row['id']}", use_container_width=True):
                            delete_feedback(row["id"])
                            st.cache_data.clear()
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗑️ Offres retirées du site":
    st.title("🗑️ Offres retirées du site")
    if df_removed.empty:
        st.info("Aucune offre retirée.")
    else:
        st.caption(f"{len(df_removed)} offres retirées")
        df_r = df_removed[["title","metier","hopital","contrat","last_seen"]].copy()
        df_r.columns = ["Titre","Métier","Hôpital","Contrat","Dernière vue"]
        st.dataframe(df_r, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
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