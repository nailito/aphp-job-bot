#dashboard.py
import json
import os
import psycopg as psycopg2
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timezone, timedelta

from config import EXCLUDED_METIERS
from database_hcl import (
    save_feedback_hcl,
    get_feedbacks_hcl_simple,
    delete_feedback_hcl,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")

st.set_page_config(page_title="Veille Emploi", page_icon="🏥", layout="wide")

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════

CATEGORY_LABELS = {
    "metier_exclu":        "Hors métier / contrat ciblé",
    "diplome_paramedical": "Diplôme paramédical requis",
    "surqualification":    "Surqualification / poste non-cadre",
    "passed_filter_1":     "✅ Passe filtre",
    "profil_inadequat":    "Profil inadéquat",
    "rejected_hcl":        "❌ Rejeté filtre HCL",
}

SOURCE_CONFIG = {
    "APHP": {
        "label":    "🏥 AP-HP",
        "color":    "#6366f1",
        "table":    "jobs",
        "icon":     "🏥",
    },
    "HCL": {
        "label":    "🏨 HCL",
        "color":    "#0ea5e9",
        "table":    "hcl_jobs",
        "icon":     "🏨",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# CONNEXION
# ══════════════════════════════════════════════════════════════════════════════

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


# ══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT & NORMALISATION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_aphp() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, title, metier, filiere, hopital, location,
               contrat, teletravail, date_publication, url, score,
               priorite, score_raison, score_points_forts, score_points_faibles,
               mots_cles_matches, raison, rejection_category, description,
               rejection_reason, first_seen, last_seen, status, scored_at
        FROM jobs
    """, conn)
    conn.close()
    df = df.drop_duplicates(subset="id")
    df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    df["first_seen"]       = pd.to_datetime(df["first_seen"],       errors="coerce")
    df["scored_at"]        = pd.to_datetime(df["scored_at"],        errors="coerce")
    df["_source"] = "APHP"
    return df


def _parse_score_analysis(raw) -> pd.Series:
    """
    Désérialise le JSON stocké dans score_analysis (scorer_hcl).
    Format attendu :
      {"priorite": "P2", "raison": "...", "points_forts": [...], "points_faibles": [...]}
    Fallback gracieux si le champ est vide ou contient du texte brut.
    """
    empty = pd.Series({
        "score_raison":       None,
        "priorite":           "–",
        "score_points_forts":  None,
        "score_points_faibles": None,
    })
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return empty
    try:
        parsed = json.loads(raw)
        return pd.Series({
            "score_raison":       parsed.get("raison", "") or "",
            "priorite":           parsed.get("priorite", "–") or "–",
            "score_points_forts":  json.dumps(parsed.get("points_forts", []),  ensure_ascii=False),
            "score_points_faibles": json.dumps(parsed.get("points_faibles", []), ensure_ascii=False),
        })
    except (json.JSONDecodeError, TypeError):
        # Texte brut legacy ou erreur de parse → on l'affiche tel quel comme raison
        return pd.Series({
            "score_raison":       str(raw),
            "priorite":           "–",
            "score_points_forts":  None,
            "score_points_faibles": None,
        })


@st.cache_data(ttl=30)
def load_hcl() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, titre, url, localisation, contrats,
            duree, date_debut, description,
            status, miss_count,
            ai_filter_decision, ai_filter_reason,
            score, score_analysis, scored_at,
            first_seen_at, last_seen_at, date_publication
        FROM hcl_jobs
    """, conn)
    conn.close()
    df = df.drop_duplicates(subset="id")

    # ── Renommages de base (sans score_analysis, traité séparément)
    df = df.rename(columns={
        "titre":            "title",
        "localisation":     "location",
        "contrats":         "contrat",
        "ai_filter_reason": "rejection_reason",
        "first_seen_at":    "first_seen",
        "last_seen_at":     "last_seen",
    })

    # ── Parse score_analysis → score_raison, priorite, points_forts, points_faibles
    parsed = df["score_analysis"].apply(_parse_score_analysis)
    df["score_raison"]        = parsed["score_raison"]
    df["priorite"]            = parsed["priorite"]
    df["score_points_forts"]  = parsed["score_points_forts"]
    df["score_points_faibles"] = parsed["score_points_faibles"]
    df = df.drop(columns=["score_analysis"])

    # ── Mapping rejection_category depuis ai_filter_decision
    def _map_cat(row):
        d = row.get("ai_filter_decision")
        if d == "pass":
            return "passed_filter_1"
        if d == "reject":
            reason = str(row.get("rejection_reason") or "").lower()
            if "paramédical" in reason or "paramedical" in reason:
                return "diplome_paramedical"
            return "surqualification"
        return None

    df["rejection_category"] = df.apply(_map_cat, axis=1)

    # ── Colonnes absentes dans HCL
    df["hopital"]          = ""
    df["metier"]           = ""
    df["filiere"]          = ""
    df["date_publication"] = pd.to_datetime(df["date_publication"], errors="coerce")
    first_seen_naive = df["first_seen"].dt.tz_localize(None) if df["first_seen"].dt.tz is not None else df["first_seen"]
    df["date_publication"] = df["date_publication"].fillna(first_seen_naive)
    df["first_seen"]       = pd.to_datetime(df["first_seen"], errors="coerce")
    df["scored_at"]        = pd.to_datetime(df["scored_at"],  errors="coerce")
    df["_source"]          = "HCL"
    return df


def load_data(source: str) -> pd.DataFrame:
    return load_aphp() if source == "APHP" else load_hcl()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — sélecteur de source + navigation
# ══════════════════════════════════════════════════════════════════════════════

if "source" not in st.session_state:
    st.session_state.source = "APHP"
if "nav" not in st.session_state:
    st.session_state.nav = "📊 Tableau de bord"

st.sidebar.title("🏥 Veille Emploi")

col_aphp, col_hcl = st.sidebar.columns(2)
with col_aphp:
    if st.button("🏥 AP-HP", use_container_width=True,
                 type="primary" if st.session_state.source == "APHP" else "secondary"):
        st.session_state.source = "APHP"
        st.rerun()
with col_hcl:
    if st.button("🏨 HCL", use_container_width=True,
                 type="primary" if st.session_state.source == "HCL" else "secondary"):
        st.session_state.source = "HCL"
        st.rerun()

source = st.session_state.source
cfg    = SOURCE_CONFIG[source]

# Chargement des données
try:
    df_all = load_data(source)
except Exception as e:
    st.error(f"Erreur de connexion à la base de données : {e}")
    st.stop()

df_active  = df_all[df_all["status"] == "active"]
df_removed = df_all[df_all["status"] == "removed"]
df_new     = df_active[df_active["first_seen"].dt.date == datetime.now().date()]

st.sidebar.caption(f"Sync : {str(df_all['last_seen'].max())[:16]}")
st.sidebar.divider()

# Navigation — pages communes aux deux sources
PAGES_SHARED = [
    "📊 Tableau de bord",
    "🔍 Explorer les offres",
    "✅ Offres acceptées par le filtre",
    "📰 Rapport du jour",
]

PAGES_APHP = [
    "🚀 À postuler",
    "📨 Mes candidatures",
    "📝 À évaluer",
    "🆕 Nouvelles offres",
    "🗑️ Offres retirées du site",
    "⚙️  Config",
]
 
PAGES_HCL = [
    "📝 À évaluer HCL",
    "🚀 À postuler HCL",
]
 
if source == "APHP":
    pages = PAGES_SHARED + PAGES_APHP
else:
    pages = PAGES_SHARED + PAGES_HCL

if st.session_state.nav not in pages:
    st.session_state.nav = "📊 Tableau de bord"

page = st.sidebar.radio("Navigation", pages,
                        index=pages.index(st.session_state.nav))


# ══════════════════════════════════════════════════════════════════════════════
# 📊 TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════════════════════

if page == "📊 Tableau de bord":
    st.title(f"📊 Tableau de bord — {cfg['label']}")

    # ── Dernier run pipeline
    conn = get_connection()
    try:
        if source == "APHP":
            runs = pd.read_sql(
                "SELECT * FROM pipeline_runs ORDER BY run_date DESC LIMIT 1", conn
            )
            if not runs.empty:
                last        = runs.iloc[0]
                run_date_str = str(last["run_date"])[:16].replace("T", " ") if last["run_date"] is not None else "–"
                date_fmt     = run_date_str[:10].replace("-", "/")
                heure_fmt    = run_date_str[11:16].replace(":", "h")
                is_ok        = str(last["status"]).startswith("success") or last["status"] == "no_new_offers"
                st.info(f"{'✅' if is_ok else '❌'} Dernière actualisation le **{date_fmt}** à **{heure_fmt}** — `{last['status']}`")
        else:
            runs = pd.read_sql(
                "SELECT * FROM pipeline_runs WHERE source = 'hcl' ORDER BY run_at DESC LIMIT 1", conn
            )
            if not runs.empty:
                last     = runs.iloc[0]
                run_at   = str(last["run_at"])[:16].replace("T", " ")
                date_fmt  = run_at[:10].replace("-", "/")
                heure_fmt = run_at[11:16].replace(":", "h")
                st.info(f"✅ Dernière actualisation HCL le **{date_fmt}** à **{heure_fmt}**")
    except Exception:
        st.warning("⚠️ Impossible de lire le dernier run pipeline.")
    finally:
        conn.close()

    st.divider()

    # ── APHP : meilleure offre évaluée + boutons navigation
    if source == "APHP":
        from database import get_feedbacks
        feedbacks         = get_feedbacks()
        feedbacks_positifs = {f["job_id"] for f in feedbacks if f["decision"] in ["⭐", "👍"]}

        with get_connection() as conn:
            df_already_applied = pd.read_sql("SELECT job_id FROM applications", conn)
        already_applied_ids = set(df_already_applied["job_id"].tolist())

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        df_top = df_active[
            df_active["id"].isin(feedbacks_positifs) &
            df_active["score"].notna() &
            ~df_active["id"].isin(already_applied_ids) &
            (pd.to_datetime(df_active["date_publication"], utc=True, errors="coerce") >= cutoff)
        ].copy()

        if not df_top.empty:
            df_top["score_num"] = pd.to_numeric(df_top["score"], errors="coerce")
            best = df_top.sort_values("score_num", ascending=False).iloc[0]
            st.markdown("### 🏆 Meilleure offre évaluée")
            col_card, col_btn = st.columns([4, 1])
            with col_card:
                score_val = int(best["score"]) if pd.notna(best["score"]) else "–"
                date_pub  = best["date_publication"].strftime("%d/%m/%Y") if pd.notna(best.get("date_publication")) else "–"
                st.markdown(f"""
                <div style="background:#f0f9ff;border-left:4px solid #6366f1;padding:16px;border-radius:8px;color:#111">
                    <div style="font-size:1.2rem;font-weight:700">{best['title']}</div>
                    <div style="color:#444;margin-top:4px">🏥 {best['hopital']} · 📍 {best['location']} · 📄 {best['contrat']} · 📅 {date_pub}</div>
                    <div style="margin-top:8px">🎯 <b>Score : {score_val}/100</b> · Priorité : <b>{best.get('priorite','–')}</b></div>
                    <div style="color:#555;margin-top:6px;font-size:0.9rem">{best.get('score_raison','')}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_btn:
                st.markdown("<br><br>", unsafe_allow_html=True)
                st.link_button("🚀 Postuler →", best["url"], use_container_width=True, type="primary")

            st.divider()

        feedbacks_existants = {f["job_id"] for f in feedbacks}
        n_a_evaluer  = len(df_active[
            (df_active["rejection_category"] == "passed_filter_1") &
            (~df_active["id"].isin(feedbacks_existants))
        ])
        n_a_postuler = len(df_active[
            df_active["id"].isin(feedbacks_positifs) &
            ~df_active["id"].isin(already_applied_ids) &
            (pd.to_datetime(df_active["date_publication"], utc=True, errors="coerce") >= cutoff)
        ])
        col_ev, col_pos = st.columns(2)
        with col_ev:
            if st.button(f"📝 Offres à évaluer\n\n{n_a_evaluer}", use_container_width=True):
                st.session_state.nav = "📝 À évaluer"
                st.rerun()
        with col_pos:
            if st.button(f"🚀 Offres à postuler\n\n{n_a_postuler}", use_container_width=True):
                st.session_state.nav = "🚀 À postuler"
                st.rerun()
        st.divider()

    # ── HCL : KPIs simples
    else:
        n_total   = len(df_active)
        n_pass    = len(df_active[df_active["rejection_category"] == "passed_filter_1"])
        n_reject  = len(df_active[df_active["rejection_category"].isin(["diplome_paramedical","surqualification"])])
        n_pending = len(df_active[df_active["rejection_category"].isna()])
        n_scored  = len(df_active[df_active["score"].notna()])
    
        # Feedbacks HCL
        with get_connection() as _conn:
            _fb_hcl = get_feedbacks_hcl_simple(_conn)
        _fb_positifs_hcl = {f["job_id"] for f in _fb_hcl if f["decision"] in ("⭐", "👍")}
        _fb_existants_hcl = {f["job_id"] for f in _fb_hcl}
    
        n_a_evaluer_hcl = len(df_active[
            (df_active["rejection_category"] == "passed_filter_1") &
            (~df_active["id"].isin(_fb_existants_hcl))
        ])
        n_a_postuler_hcl = len(df_active[
            df_active["id"].isin(_fb_positifs_hcl)
        ])
    
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("📋 Offres actives",  n_total)
        c2.metric("✅ Retenues filtre", n_pass)
        c3.metric("❌ Rejetées filtre", n_reject)
        c4.metric("⏳ Sans décision",   n_pending)
        c5.metric("🎯 Scorées",         n_scored)
    
        if n_scored > 0:
            df_sc = df_active[df_active["score"].notna()]
            p1 = len(df_sc[df_sc["priorite"] == "P1"])
            p2 = len(df_sc[df_sc["priorite"] == "P2"])
            p3 = len(df_sc[df_sc["priorite"] == "P3"])
            st.caption(f"Scorées — 🟢 P1 : {p1} · 🟡 P2 : {p2} · 🔴 P3 : {p3}")
    
        st.divider()
    
        col_ev_hcl, col_pos_hcl = st.columns(2)
        with col_ev_hcl:
            if st.button(f"📝 À évaluer\n\n{n_a_evaluer_hcl}", use_container_width=True):
                st.session_state.nav = "📝 À évaluer HCL"
                st.rerun()
        with col_pos_hcl:
            if st.button(f"🚀 À postuler\n\n{n_a_postuler_hcl}", use_container_width=True):
                st.session_state.nav = "🚀 À postuler HCL"
                st.rerun()

        st.divider()

    # ── Camembert commun
    n_total_actif = len(df_active)

    if source == "APHP":
        n_rej_metier      = len(df_active[df_active["rejection_category"] == "metier_exclu"])
        n_rej_ia          = len(df_active[df_active["rejection_category"].isin(["diplome_paramedical","surqualification","profil_inadequat"])])
        n_scored_val      = len(df_active[df_active["score"].notna()])
        n_passed_no_score = len(df_active[(df_active["rejection_category"] == "passed_filter_1") & df_active["score"].isna()])

        labels = ["❌ Filtre métier/contrat", "🤖 Rejeté filtre IA", "⏳ Passé IA (sans score)", "🎯 Scorées"]
        values = [n_rej_metier, n_rej_ia, n_passed_no_score, n_scored_val]
        colors = ["#f87171", "#fb923c", "#a78bfa", "#34d399"]
        title  = f"Répartition des {n_total_actif:,} offres APHP actives"
    else:
        n_pass    = len(df_active[df_active["rejection_category"] == "passed_filter_1"])
        n_reject  = len(df_active[df_active["rejection_category"].isin(["diplome_paramedical","surqualification"])])
        n_pending = len(df_active[df_active["rejection_category"].isna()])
        n_scored  = len(df_active[df_active["score"].notna()])

        labels = ["✅ Retenues (non scorées)", "❌ Rejetées", "⏳ Sans décision", "🎯 Scorées"]
        values = [max(n_pass - n_scored, 0), n_reject, n_pending, n_scored]
        colors = ["#34d399", "#f87171", "#94a3b8", "#0ea5e9"]
        title  = f"Répartition des {n_total_actif:,} offres HCL actives"

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.45,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hovertemplate="%{label}<br>%{value} offres<br>%{percent}<extra></extra>",
    )])
    fig.update_layout(
        title=dict(text=title, x=0.5),
        showlegend=False,
        margin=dict(t=60, b=20, l=20, r=20),
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# 🔍 EXPLORER LES OFFRES
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🔍 Explorer les offres":
    st.title(f"🔍 Explorer les offres — {cfg['label']}")

    with st.expander("Filtres", expanded=True):
        col1, col2, col3 = st.columns(3)
        search = col1.text_input("Recherche titre", "")

        if source == "APHP":
            filiere_opts = ["Toutes"] + sorted(df_active["filiere"].dropna().unique().tolist())
            filiere_sel  = col2.selectbox("Filière", filiere_opts)
        else:
            loc_opts  = ["Tous"] + sorted(df_active["location"].dropna().str.split(",").explode().str.strip().unique().tolist())
            loc_sel   = col2.selectbox("Localisation", loc_opts)

        contrat_opts = ["Tous"] + sorted(df_active["contrat"].dropna().unique().tolist())
        contrat_sel  = col3.selectbox("Contrat", contrat_opts)

        col4, col5 = st.columns(2)
        only_passed = col4.checkbox("Uniquement offres retenues par le filtre", value=False)
        if source == "APHP":
            exclure = col5.checkbox("Exclure filtre métiers/contrats", value=True)

    df_view = df_active.copy()

    if source == "APHP" and exclure:
        df_view = df_view[df_view["rejection_category"] != "metier_exclu"]
    if search:
        df_view = df_view[df_view["title"].str.contains(search, case=False, na=False)]
    if source == "APHP" and filiere_sel != "Toutes":
        df_view = df_view[df_view["filiere"] == filiere_sel]
    if source == "HCL" and loc_sel != "Tous":
        df_view = df_view[df_view["location"].str.contains(loc_sel, case=False, na=False)]
    if contrat_sel != "Tous":
        df_view = df_view[df_view["contrat"].str.contains(contrat_sel, case=False, na=False)]
    if only_passed:
        df_view = df_view[df_view["rejection_category"] == "passed_filter_1"]

    df_view = df_view.sort_values("date_publication", ascending=False)
    st.caption(f"{len(df_view)} offres")

    df_d = df_view.copy()
    df_d["statut_score"] = df_d.apply(
        lambda r: f"✅ {int(r['score'])}/100 [{r.get('priorite','–')}]" if pd.notna(r.get("score")) else
                  ("✅ Retenue" if r.get("rejection_category") == "passed_filter_1" else
                   CATEGORY_LABELS.get(r.get("rejection_category",""), r.get("rejection_category","") or "⏳ En attente")),
        axis=1
    )
    df_d["raison"] = df_d.apply(
        lambda r: r.get("score_raison") or r.get("rejection_reason") or "–", axis=1
    )

    if source == "APHP":
        cols_show = ["title","statut_score","raison","hopital","date_publication","url"]
        col_labels = ["Titre","Statut / Score","Analyse / Raison","Hôpital","Publiée le","Lien"]
    else:
        cols_show = ["title","statut_score","raison","location","contrat","date_publication","url"]
        col_labels = ["Titre","Statut","Raison / Analyse","Localisation","Contrat","Première vue","Lien"]

    df_d = df_d[cols_show].copy()
    df_d.columns = col_labels

    st.dataframe(df_d, use_container_width=True, hide_index=True,
        column_config={
            "Lien":               st.column_config.LinkColumn("Lien", display_text="Voir →"),
            "Titre":              st.column_config.TextColumn(width="large"),
            "Statut / Score":     st.column_config.TextColumn(width="small"),
            "Statut":             st.column_config.TextColumn(width="small"),
            "Analyse / Raison":   st.column_config.TextColumn(width="large"),
            "Raison / Analyse":   st.column_config.TextColumn(width="large"),
            "Publiée le":         st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
            "Première vue":       st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
        })

    st.divider()
    selected = st.selectbox("Détail d'une offre", ["–"] + df_view["title"].tolist())
    if selected != "–":
        row = df_view[df_view["title"] == selected].iloc[0]
        st.markdown(f"### {row['title']}")
        if source == "APHP":
            st.markdown(f"**🏥 {row['hopital']}** · 📍 {row['location']} · {row['contrat']}")
        else:
            st.markdown(f"📍 {row['location']} · 📄 {row['contrat']}")

        # Analyse IA si scorée
        if pd.notna(row.get("score")):
            score_val = int(row["score"])
            prio      = row.get("priorite", "–")
            emoji     = "🟢" if score_val >= 80 else "🟡" if score_val >= 60 else "🔴"
            st.markdown(f"{emoji} **{score_val}/100** · Priorité **{prio}**")
            if pd.notna(row.get("score_raison")) and row["score_raison"]:
                st.info(row["score_raison"])
            try:
                pf = json.loads(row.get("score_points_forts") or "[]")
                pp = json.loads(row.get("score_points_faibles") or "[]")
                if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
            except Exception:
                pass

        if pd.notna(row.get("description")) and row["description"]:
            with st.expander("Description complète"):
                st.markdown(str(row["description"])[:3000], unsafe_allow_html=False)
        st.link_button("Voir l'offre →", row["url"])


# ══════════════════════════════════════════════════════════════════════════════
# ✅ OFFRES ACCEPTÉES PAR LE FILTRE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "✅ Offres acceptées par le filtre":
    st.title(f"✅ Offres retenues par le filtre — {cfg['label']}")

    df_passed = df_active[df_active["rejection_category"] == "passed_filter_1"].copy()

    if df_passed.empty:
        st.info("Aucune offre retenue pour l'instant. Lance le pipeline pour analyser les offres.")
        st.stop()

    df_scorees     = df_passed[df_passed["score"].notna()].sort_values("score", ascending=False)
    df_non_scorees = df_passed[df_passed["score"].isna()]
    st.caption(f"{len(df_passed)} offres retenues — {len(df_scorees)} scorées, {len(df_non_scorees)} en attente")

    tab_scorees, tab_non_scorees = st.tabs([
        f"🎯 Scorées ({len(df_scorees)})",
        f"⏳ En attente de score ({len(df_non_scorees)})",
    ])

    with tab_scorees:
        if df_scorees.empty:
            st.info("Aucune offre scorée.")
        else:
            if source == "APHP":
                cols = ["score","priorite","title","metier","filiere","hopital","location","contrat","score_raison","url"]
                labels = ["Score","Priorité","Titre","Métier","Filière","Hôpital","Lieu","Contrat","Analyse IA","URL"]
            else:
                cols = ["score","priorite","title","location","contrat","score_raison","url"]
                labels = ["Score","Priorité","Titre","Localisation","Contrat","Analyse IA","URL"]

            df_s = df_scorees[cols].copy()
            df_s.columns = labels
            st.dataframe(df_s, use_container_width=True, hide_index=True,
                column_config={
                    "URL":        st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Titre":      st.column_config.TextColumn(width="large"),
                    "Analyse IA": st.column_config.TextColumn(width="large"),
                    "Score":      st.column_config.NumberColumn(format="%d/100"),
                    "Priorité":   st.column_config.TextColumn(width="small"),
                })

            # ── Détail points forts/faibles pour HCL
            if source == "HCL":
                st.divider()
                selected_s = st.selectbox(
                    "Détail d'une offre scorée",
                    ["–"] + df_scorees["title"].tolist(),
                    key="detail_scoree_hcl"
                )
                if selected_s != "–":
                    row = df_scorees[df_scorees["title"] == selected_s].iloc[0]
                    score_val = int(row["score"])
                    prio      = row.get("priorite", "–")
                    emoji     = "🟢" if score_val >= 80 else "🟡" if score_val >= 60 else "🔴"
                    st.markdown(f"### {row['title']}")
                    st.markdown(f"📍 {row['location']} · 📄 {row['contrat']} · {emoji} **{score_val}/100** · Priorité **{prio}**")
                    if pd.notna(row.get("score_raison")) and row["score_raison"]:
                        st.info(row["score_raison"])
                    try:
                        pf = json.loads(row.get("score_points_forts") or "[]")
                        pp = json.loads(row.get("score_points_faibles") or "[]")
                        c1, c2 = st.columns(2)
                        with c1:
                            if pf:
                                st.markdown("**✅ Points forts**")
                                for p in pf: st.markdown(f"- {p}")
                        with c2:
                            if pp:
                                st.markdown("**⚠️ Points faibles**")
                                for p in pp: st.markdown(f"- {p}")
                    except Exception:
                        pass
                    st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")

    with tab_non_scorees:
        if df_non_scorees.empty:
            st.info("Toutes les offres retenues ont été scorées.")
        else:
            if source == "APHP":
                cols = ["title","metier","filiere","hopital","location","contrat","url"]
                labels = ["Titre","Métier","Filière","Hôpital","Lieu","Contrat","URL"]
            else:
                cols = ["title","location","contrat","rejection_reason","url"]
                labels = ["Titre","Localisation","Contrat","Raison passage","URL"]

            df_ns = df_non_scorees[cols].copy()
            df_ns.columns = labels
            st.dataframe(df_ns, use_container_width=True, hide_index=True,
                column_config={
                    "URL":            st.column_config.LinkColumn("Lien", display_text="Voir →"),
                    "Titre":          st.column_config.TextColumn(width="large"),
                    "Raison passage": st.column_config.TextColumn(width="large"),
                })
            st.info("Active `scoring_enabled = True` dans `pipeline_hcl.py` pour scorer ces offres.")


# ══════════════════════════════════════════════════════════════════════════════
# 📰 RAPPORT DU JOUR
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📰 Rapport du jour":
    st.title(f"📰 Rapport du jour — {cfg['label']}")

    conn = get_connection()
    try:
        if source == "APHP":
            runs = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY run_date DESC LIMIT 30", conn)
        else:
            runs = pd.read_sql(
                "SELECT * FROM pipeline_runs WHERE source = 'hcl' ORDER BY run_at DESC LIMIT 30", conn
            )
    except Exception as e:
        st.warning(f"Impossible de lire l'historique des runs : {e}")
        runs = pd.DataFrame()
    finally:
        conn.close()

    if runs.empty:
        st.info("Aucun pipeline exécuté.")
        st.stop()

    last = runs.iloc[0]

    if source == "APHP":
        run_date = str(last["run_date"])[:10] if last["run_date"] is not None else "–"
        n_new_last  = last["n_new"]
        n_scr_last  = last["n_scraped"]
        n_rem_last  = last["n_removed"]
        n_pass_last = last["n_passed_ai"]
        n_scr_val   = last["n_scored"]
        status_val  = last["status"]
        dur_col     = "duration_sec"
    else:
        run_date    = str(last["run_at"])[:10]
        n_new_last  = last.get("new_offers", 0)
        n_scr_last  = last.get("total_scraped", 0)
        n_rem_last  = last.get("removed_offers", 0)
        n_pass_last = last.get("ai_passed", 0)
        n_scr_val   = last.get("scored", 0)
        status_val  = "–"
        dur_col     = None

    if n_new_last == 0:
        st.success(f"✅ Dernier run le {run_date} — Aucune nouvelle offre")
    else:
        st.info(f"📅 Dernier run le {run_date} — **{n_new_last} nouvelles offres** détectées")

    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🌐 Scrapées",   f"{n_scr_last:,}")
    c2.metric("🆕 Nouvelles",  f"{n_new_last:,}")
    c3.metric("🗑️ Retirées",   f"{n_rem_last:,}")
    c4.metric("✅ Passées",    f"{n_pass_last:,}")
    c5.metric("🎯 Scorées",    f"{n_scr_val:,}")

    st.divider()

    # ── Offres du dernier run
    try:
        ref_date = pd.Timestamp(run_date).date()
    except Exception:
        ref_date = datetime.now().date()
    df_nouvelles = df_active[df_active["first_seen"].dt.date == ref_date].copy()

    if not df_nouvelles.empty:
        n_p = len(df_nouvelles[df_nouvelles["rejection_category"] == "passed_filter_1"])
        n_r = len(df_nouvelles[df_nouvelles["rejection_category"].isin(["metier_exclu","diplome_paramedical","surqualification","profil_inadequat"])])
        n_s = len(df_nouvelles[df_nouvelles["score"].notna()])

        tab1, tab2, tab3 = st.tabs([f"✅ Retenues ({n_p})", f"❌ Rejetées ({n_r})", f"🎯 Scorées ({n_s})"])

        with tab1:
            df_p = df_nouvelles[df_nouvelles["rejection_category"] == "passed_filter_1"]
            if df_p.empty:
                st.info("Aucune offre retenue lors de ce run.")
            else:
                df_p = df_p.sort_values("score", ascending=False, na_position="last")
                for _, row in df_p.iterrows():
                    score   = int(row["score"]) if pd.notna(row.get("score")) else "–"
                    prio    = row.get("priorite", "–")
                    emoji   = "🟢" if isinstance(score, int) and score >= 80 else "🟡" if isinstance(score, int) and score >= 60 else "⚪"
                    loc     = row.get("hopital") or row.get("location","")
                    header  = f"{emoji} {score}/100 [{prio}] — **{row['title']}** — {loc}" if score != "–" else f"⚪ **{row['title']}** — {loc}"

                    with st.expander(header):
                        if score != "–":
                            c1, c2 = st.columns(2)
                            c1.metric("Score", f"{score}/100")
                            c2.metric("Priorité", prio)
                        if pd.notna(row.get("score_raison")) and row["score_raison"]:
                            st.info(row["score_raison"])
                            try:
                                pf = json.loads(row.get("score_points_forts") or "[]")
                                pp = json.loads(row.get("score_points_faibles") or "[]")
                                if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                                if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                            except Exception:
                                pass
                        reason = row.get("rejection_reason","")
                        if reason and not pd.isna(reason):
                            st.caption(f"Raison passage : {reason}")
                        st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")

        with tab2:
            df_r = df_nouvelles[df_nouvelles["rejection_category"].isin(
                ["metier_exclu","diplome_paramedical","surqualification","profil_inadequat"]
            )]
            if df_r.empty:
                st.info("Aucune offre rejetée lors de ce run.")
            else:
                for _, row in df_r.iterrows():
                    cat    = CATEGORY_LABELS.get(row.get("rejection_category",""), row.get("rejection_category",""))
                    raison = row.get("rejection_reason") or "–"
                    loc    = row.get("hopital") or row.get("location","")

                    with st.expander(f"❌ **{row['title']}** — {loc}"):
                        st.markdown(f"**Catégorie :** {cat}")
                        st.markdown(f"**Raison :** {raison}")
                        st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")

        with tab3:
            df_s = df_nouvelles[df_nouvelles["score"].notna()].sort_values("score", ascending=False)
            if df_s.empty:
                st.info("Aucune offre scorée lors de ce run.")
            else:
                for _, row in df_s.iterrows():
                    score = int(row["score"])
                    prio  = row.get("priorite", "–")
                    emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
                    loc   = row.get("hopital") or row.get("location","")

                    with st.expander(f"{emoji} {score}/100 [{prio}] — **{row['title']}** — {loc}"):
                        c1, c2 = st.columns(2)
                        c1.metric("Score", f"{score}/100")
                        c2.metric("Priorité", prio)
                        if pd.notna(row.get("score_raison")) and row["score_raison"]:
                            st.info(row["score_raison"])
                            try:
                                pf = json.loads(row.get("score_points_forts") or "[]")
                                pp = json.loads(row.get("score_points_faibles") or "[]")
                                if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                                if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                            except Exception:
                                pass
                        st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")

    st.divider()
    st.subheader("📈 Historique des runs")

    if source == "APHP":
        runs_d = runs[["run_date","n_new","n_removed","n_passed_ai","n_scored","status","duration_sec"]].copy()
        runs_d["run_date"]     = runs_d["run_date"].str[:16]
        runs_d["duration_sec"] = runs_d["duration_sec"].apply(lambda x: f"{x}s")
        runs_d.columns = ["Date","Nouvelles","Retirées","Passées","Scorées","Statut","Durée"]
    else:
        col_map = {
            "run_at":           "Date",
            "new_offers":       "Nouvelles",
            "removed_offers":   "Retirées",
            "ai_passed":        "Passées",
            "scored":           "Scorées",
            "total_scraped":    "Scrapées",
        }
        available = {k: v for k, v in col_map.items() if k in runs.columns}
        runs_d = runs[list(available.keys())].copy()
        runs_d.columns = list(available.values())
        if "Date" in runs_d.columns:
            runs_d["Date"] = runs_d["Date"].astype(str).str[:16]

    st.dataframe(runs_d, use_container_width=True, hide_index=True)

    if source == "APHP":
        st.divider()
        st.subheader("🚀 Lancer le pipeline manuellement")
        if st.button("▶️ Déclencher le pipeline via GitHub Actions", use_container_width=True, type="primary"):
            import requests
            gh_token = os.getenv("GH_WORKFLOW_TOKEN","")
            if not gh_token:
                st.error("❌ Secret GH_WORKFLOW_TOKEN manquant.")
            else:
                resp = requests.post(
                    "https://api.github.com/repos/nailito/aphp-job-bot/actions/workflows/daily.yml/dispatches",
                    headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
                    json={"ref": "main"},
                )
                if resp.status_code == 204:
                    st.success("✅ Pipeline déclenché !")
                else:
                    st.error(f"❌ Erreur GitHub API : {resp.status_code}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGES APHP UNIQUEMENT (conservées à l'identique)
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🚀 À postuler":
    st.title("🚀 Offres à postuler")

    from database import get_feedbacks
    feedbacks          = get_feedbacks()
    feedbacks_positifs = {f["job_id"] for f in feedbacks if f["decision"] in ["⭐", "👍"]}

    with get_connection() as conn:
        df_already_applied = pd.read_sql("SELECT job_id FROM applications", conn)
    already_applied_ids = set(df_already_applied["job_id"].tolist())

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    df_postuler = df_active[
        df_active["id"].isin(feedbacks_positifs) &
        ~df_active["id"].isin(already_applied_ids) &
        (pd.to_datetime(df_active["date_publication"], utc=True, errors="coerce") >= cutoff)
    ].copy()

    if df_postuler.empty:
        st.info("Aucune offre à postuler — évalue des offres dans **📝 À évaluer**.")
        st.stop()

    df_postuler["score_num"] = pd.to_numeric(df_postuler["score"], errors="coerce")
    df_postuler = df_postuler.sort_values("score_num", ascending=False).reset_index(drop=True)

    if "selected_job_apply" not in st.session_state:
        st.session_state.selected_job_apply = df_postuler.iloc[0]["id"]

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader(f"📋 {len(df_postuler)} offres")
        for _, row in df_postuler.iterrows():
            job_id = row["id"]
            score  = int(row["score"]) if pd.notna(row["score"]) else "–"
            dec_emoji = "⭐" if job_id in {f["job_id"] for f in feedbacks if f["decision"] == "⭐"} else "👍"
            label  = f"{dec_emoji} {row['title'][:35]}... ({score}/100)"
            active = job_id == st.session_state.selected_job_apply
            if st.button(label, key=f"apply_{job_id}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.selected_job_apply = job_id
                st.rerun()

    with col_right:
        job    = df_postuler[df_postuler["id"] == st.session_state.selected_job_apply].iloc[0]
        job_id = job["id"]

        st.subheader(job["title"])
        st.markdown(f"**🏥 {job['hopital']}** · 📍 {job['location']} · 📄 {job['contrat']}")

        score = int(job["score"]) if pd.notna(job["score"]) else "–"
        date_pub = job["date_publication"].strftime("%d/%m/%Y") if pd.notna(job.get("date_publication")) else "–"
        c1, c2 = st.columns(2)
        c1.metric("Score", f"{score}/100")
        c2.metric("Publiée le", date_pub)

        if pd.notna(job.get("score_raison")):
            with st.expander("🧠 Analyse IA"):
                st.write(job["score_raison"])
                try:
                    pf = json.loads(job.get("score_points_forts") or "[]")
                    pp = json.loads(job.get("score_points_faibles") or "[]")
                    if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                    if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                except Exception:
                    pass

        st.divider()
        st.link_button("🚀 Postuler sur APHP →", job["url"], use_container_width=True, type="primary")


elif page == "📨 Mes candidatures":
    st.title("📨 Mes candidatures")

    STATUTS = ["👀 En cours d'examen", "📞 Entretien planifié", "✅ Offre reçue", "❌ Refusée"]

    with st.expander("➕ Ajouter une candidature", expanded=False):
        from database import get_feedbacks
        feedbacks          = get_feedbacks()
        feedbacks_positifs = {f["job_id"] for f in feedbacks if f["decision"] in ["⭐", "👍"]}
        df_eligible        = df_active[df_active["id"].isin(feedbacks_positifs)].copy()

        with get_connection() as conn:
            df_apps_check = pd.read_sql("SELECT job_id FROM applications", conn)
        already_applied = set(df_apps_check["job_id"].tolist())
        df_eligible = df_eligible[~df_eligible["id"].isin(already_applied)]

        if df_eligible.empty:
            st.info("Toutes tes offres évaluées positivement ont déjà une candidature.")
        else:
            df_eligible["label"] = df_eligible.apply(lambda r: f"{r['title']} — {r['hopital']}", axis=1)
            choix    = st.selectbox("Sélectionne l'offre", df_eligible["label"].tolist())
            job_row  = df_eligible[df_eligible["label"] == choix].iloc[0]

            c1, c2       = st.columns(2)
            statut_new   = c1.selectbox("Statut initial", STATUTS)
            date_cand_new = c2.date_input("Date de candidature", value=datetime.now().date())
            notes_new    = st.text_area("Notes", height=80)

            if st.button("💾 Enregistrer la candidature", use_container_width=True, type="primary"):
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO applications (job_id, statut, date_candidature, notes)
                            VALUES (%s, %s, %s, %s)
                        """, (job_row["id"], statut_new, date_cand_new, notes_new))
                    conn.commit()
                st.success("✅ Candidature enregistrée !")
                st.cache_data.clear()
                st.rerun()

    st.divider()

    with get_connection() as conn:
        df_apps = pd.read_sql("""
            SELECT a.id as app_id, a.job_id, a.statut, a.date_candidature, a.notes, a.updated_at,
                   j.title, j.hopital, j.location, j.contrat, j.url, j.score, j.date_publication
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            ORDER BY a.date_candidature DESC NULLS LAST
        """, conn)

    if df_apps.empty:
        st.info("Aucune candidature enregistrée pour l'instant.")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👀 En cours",    len(df_apps[df_apps["statut"] == "👀 En cours d'examen"]))
    c2.metric("📞 Entretien",   len(df_apps[df_apps["statut"] == "📞 Entretien planifié"]))
    c3.metric("✅ Offre reçue", len(df_apps[df_apps["statut"] == "✅ Offre reçue"]))
    c4.metric("❌ Refusée",     len(df_apps[df_apps["statut"] == "❌ Refusée"]))

    st.divider()

    for _, row in df_apps.iterrows():
        score = int(row["score"]) if pd.notna(row.get("score")) else "–"
        with st.expander(f"{row['statut']} — **{row['title']}** — {row['hopital']}"):
            date_pub = str(row["date_publication"])[:10] if pd.notna(row.get("date_publication")) else "–"
            c1, c2, c3 = st.columns(3)
            c1.metric("Score", f"{score}/100")
            c2.metric("Publiée le", date_pub)
            c3.metric("Candidature", str(row["date_candidature"])[:10] if pd.notna(row.get("date_candidature")) else "–")

            st.markdown(f"**📍 {row['location']}** | **📄 {row['contrat']}**")
            if pd.notna(row.get("notes")) and row["notes"]:
                st.markdown(f"**📝 Notes :** {row['notes']}")

            st.divider()
            col_statut, col_notes = st.columns([1, 2])
            with col_statut:
                nouveau_statut = st.selectbox("Changer le statut", STATUTS,
                    index=STATUTS.index(row["statut"]) if row["statut"] in STATUTS else 0,
                    key=f"statut_{row['app_id']}")

            refus_raison = row.get("refus_raison") or ""
            if nouveau_statut == "❌ Refusée":
                refus_raison = st.text_input("Raison du refus", value=refus_raison,
                    key=f"refus_{row['app_id']}")

            with col_notes:
                nouvelles_notes = st.text_area("Mettre à jour les notes", value=row["notes"] or "",
                    height=80, key=f"notes_{row['app_id']}")

            col_save, col_del, col_link = st.columns(3)
            with col_save:
                if st.button("💾 Sauvegarder", key=f"save_app_{row['app_id']}", use_container_width=True):
                    with get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE applications
                                SET statut=%s, notes=%s, refus_raison=%s, updated_at=NOW()
                                WHERE id=%s
                            """, (nouveau_statut, nouvelles_notes, refus_raison, row["app_id"]))
                        conn.commit()
                    st.success("✅ Mis à jour !")
                    st.cache_data.clear()
                    st.rerun()
            with col_del:
                if st.button("🗑️ Supprimer", key=f"del_app_{row['app_id']}", use_container_width=True):
                    with get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM applications WHERE id=%s", (row["app_id"],))
                        conn.commit()
                    st.cache_data.clear()
                    st.rerun()
            with col_link:
                st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")


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
            tri = col_tri.selectbox("Trier par",
                ["Score (meilleur en premier)", "Score (moins bon en premier)", "Date de publication"],
                key="tri_eval")

            df_a_evaluer["score_num"] = pd.to_numeric(df_a_evaluer["score"], errors="coerce")
            if tri == "Score (meilleur en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=False, na_position="last").reset_index(drop=True)
            elif tri == "Score (moins bon en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=True, na_position="last").reset_index(drop=True)
            else:
                df_a_evaluer = df_a_evaluer.sort_values("date_publication", ascending=False).reset_index(drop=True)

            for idx, row in df_a_evaluer.iterrows():
                score_label = f"🎯 {int(row['score'])}/100 — " if pd.notna(row.get("score")) else ""
                prio_label  = f"[{row['priorite']}] " if pd.notna(row.get("priorite")) and row.get("priorite") not in ("–", None) else ""
                job_id      = row["id"]
                job_key     = f"{idx}_{job_id}"

                with st.expander(f"{score_label}{prio_label}**{row['title']}** — {row['hopital']}"):
                    date_pub = row["date_publication"].strftime("%d/%m/%Y") if pd.notna(row.get("date_publication")) else "–"
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Score", f"{int(row['score'])}/100" if pd.notna(row.get("score")) else "–")
                    c2.metric("Priorité", row.get("priorite","–"))
                    c3.metric("Publiée le", date_pub)

                    if pd.notna(row.get("score_raison")):
                        st.markdown(f"**🧠 Analyse IA :** {row['score_raison']}")

                    if st.button("✨ Générer résumé", key=f"resume_{job_key}"):
                        with st.spinner("Génération en cours..."):
                            try:
                                from groq import Groq
                                from config import GROQ_API_KEY
                                client   = Groq(api_key=GROQ_API_KEY)
                                response = client.chat.completions.create(
                                    model="llama-3.1-8b-instant", max_tokens=200,
                                    messages=[{"role":"user","content":f"""
Résume cette offre en 3 bullet points courts (max 15 mots chacun).
Focus sur : rôle principal, compétences clés, contexte/service.
Titre : {row['title']}
Description : {str(row.get('description',''))[:1500]}
"""}])
                                st.session_state[f"resume_text_{job_id}"] = response.choices[0].message.content.strip()
                            except Exception as e:
                                st.error(f"Erreur : {e}")

                    if f"resume_text_{job_id}" in st.session_state:
                        st.markdown(st.session_state[f"resume_text_{job_id}"])

                    st.divider()
                    st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True)
                    st.divider()

                    c_a, c_b, c_c = st.columns(3)
                    btn_top = c_a.button("⭐ Excellent",       key=f"top_{job_key}", use_container_width=True)
                    btn_oui = c_b.button("👍 Intéressant",     key=f"oui_{job_key}", use_container_width=True)
                    btn_non = c_c.button("👎 Pas intéressant", key=f"non_{job_key}", use_container_width=True)

                    if btn_top: st.session_state[f"dec_{job_id}"] = "⭐"
                    if btn_oui: st.session_state[f"dec_{job_id}"] = "👍"
                    if btn_non: st.session_state[f"dec_{job_id}"] = "👎"

                    if f"dec_{job_id}" in st.session_state:
                        dec = st.session_state[f"dec_{job_id}"]
                        st.markdown(f"**Décision : {dec}**")
                        commentaire = st.text_area("Ton feedback :", key=f"comment_{job_key}", height=80)
                        if st.button("💾 Sauvegarder", key=f"save_{job_key}", use_container_width=True):
                            save_feedback(job_id, dec, [], commentaire)
                            st.success("✅ Sauvegardé !")
                            st.cache_data.clear()
                            st.rerun()

    with tab_done:
        if df_deja_evalues.empty:
            st.info("Aucun feedback encore.")
        else:
            feedback_map = {f["job_id"]: f for f in get_feedbacks()}
            for _, row in df_deja_evalues.iterrows():
                f = feedback_map.get(row["id"], {})
                with st.expander(f"{f.get('decision','?')} **{row['title']}** — {row['hopital']}"):
                    st.markdown(f"**Feedback :** {f.get('commentaire','–')}")
                    st.markdown(f"**Date :** {f.get('created_at','')[:10]}")
                    c1, c2 = st.columns(2)
                    c1.link_button("Voir l'offre →", row["url"])
                    with c2:
                        if st.button("🗑️ Supprimer", key=f"del_{row['id']}", use_container_width=True):
                            delete_feedback(row["id"])
                            st.cache_data.clear()
                            st.rerun()


elif page == "🆕 Nouvelles offres":
    st.title("🆕 Nouvelles offres")
    df_nf = df_new[df_new["rejection_category"] != "metier_exclu"]
    st.caption(f"{len(df_nf)} nouvelles offres aujourd'hui")
    if df_nf.empty:
        st.info("Aucune nouvelle offre aujourd'hui.")
    else:
        for _, row in df_nf.iterrows():
            score  = int(row["score"]) if pd.notna(row.get("score")) else None
            cat    = row.get("rejection_category","")
            header = f"🆕 {score}/100 — **{row['title']}** — {row['hopital']}" if score else f"🆕 **{row['title']}** — {row['hopital']}"

            with st.expander(header):
                if score:
                    st.metric("Score", f"{score}/100")
                    if pd.notna(row.get("score_raison")):
                        st.markdown(f"**🧠 Analyse IA :** {row['score_raison']}")
                elif cat and cat != "passed_filter_1":
                    raison    = row.get("rejection_reason") or "–"
                    cat_label = CATEGORY_LABELS.get(cat, cat)
                    st.markdown(f"**Rejet :** {cat_label}")
                    st.markdown(f"**Raison :** {raison}")
                st.divider()
                st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")


elif page == "🗑️ Offres retirées du site":
    st.title("🗑️ Offres retirées du site")
    if df_removed.empty:
        st.info("Aucune offre retirée.")
    else:
        from database import get_feedbacks
        feedbacks    = get_feedbacks()
        feedback_map = {f["job_id"]: f for f in feedbacks}

        st.caption(f"{len(df_removed)} offres retirées")
        for _, row in df_removed.iterrows():
            score      = row.get("score")
            passed_ia  = pd.notna(score) and float(score) >= 50
            evaluated  = row["id"] in feedback_map
            ia_badge   = "✅ Passée IA" if passed_ia else "❌ Non passée IA"
            eval_badge = f"{feedback_map[row['id']]['decision']} Évaluée" if evaluated else "⬜ Non évaluée"

            with st.expander(f"🗑️ **{row['title']}** — {row['hopital']} | {ia_badge} | {eval_badge}"):
                c1, c2 = st.columns(2)
                c1.metric("Score IA", f"{int(score)}/100" if pd.notna(score) else "–")
                c2.metric("Dernière vue", str(row.get("last_seen",""))[:10])
                if pd.notna(score) and pd.notna(row.get("score_raison")):
                    st.markdown(f"**🧠 Analyse IA :** {row['score_raison']}")
                if evaluated:
                    f = feedback_map[row["id"]]
                    st.markdown(f"**Ton évaluation :** {f['decision']} — {f.get('commentaire','–')}")
                st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True, type="primary")


elif page == "📝 À évaluer HCL":
    st.title("📝 À évaluer — HCL")
 
    conn_eval = get_connection()
    try:
        fb_all      = get_feedbacks_hcl_simple(conn_eval)
        fb_existants = {f["job_id"] for f in fb_all}
        fb_decisions = {f["job_id"]: f["decision"] for f in fb_all}
 
        df_a_evaluer = df_active[
            (df_active["rejection_category"] == "passed_filter_1") &
            (~df_active["id"].isin(fb_existants))
        ].copy().drop_duplicates(subset="id")
 
        df_deja_evalues = df_active[
            df_active["id"].isin(fb_existants)
        ].copy()
 
    finally:
        conn_eval.close()
 
    tab_eval, tab_done = st.tabs([
        f"⏳ À évaluer ({len(df_a_evaluer)})",
        f"✅ Déjà évalués ({len(df_deja_evalues)})",
    ])
 
    # ── Onglet : À évaluer
    with tab_eval:
        if df_a_evaluer.empty:
            st.info("🎉 Toutes les offres HCL retenues ont été évaluées !")
        else:
            col_tri, _ = st.columns([1, 3])
            tri = col_tri.selectbox(
                "Trier par",
                ["Score (meilleur en premier)", "Score (moins bon en premier)", "Première vue"],
                key="tri_eval_hcl",
            )
 
            df_a_evaluer["score_num"] = pd.to_numeric(df_a_evaluer["score"], errors="coerce")
            if tri == "Score (meilleur en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=False, na_position="last")
            elif tri == "Score (moins bon en premier)":
                df_a_evaluer = df_a_evaluer.sort_values("score_num", ascending=True,  na_position="last")
            else:
                df_a_evaluer = df_a_evaluer.sort_values("first_seen", ascending=False)
 
            df_a_evaluer = df_a_evaluer.reset_index(drop=True)
 
            for idx, row in df_a_evaluer.iterrows():
                job_id    = row["id"]
                job_key   = f"hcl_{idx}_{job_id}"
                score_val = int(row["score"]) if pd.notna(row.get("score")) else None
                prio      = row.get("priorite", "–")
                emoji     = "🟢" if score_val and score_val >= 80 else "🟡" if score_val and score_val >= 60 else "🔴" if score_val else "⚪"
 
                score_label = f"{emoji} {score_val}/100 [{prio}] — " if score_val else ""
                header      = f"{score_label}**{row['title']}** — {row['location']}"
 
                with st.expander(header):
                    # Métriques
                    date_pub = row["first_seen"].strftime("%d/%m/%Y") if pd.notna(row.get("first_seen")) else "–"
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Score",      f"{score_val}/100" if score_val else "–")
                    c2.metric("Priorité",   prio)
                    c3.metric("Contrat",    row.get("contrat","–") or "–")
                    c4.metric("Première vue", date_pub)
 
                    # Analyse IA
                    if pd.notna(row.get("score_raison")) and row["score_raison"]:
                        st.info(row["score_raison"])
                    try:
                        pf = json.loads(row.get("score_points_forts") or "[]")
                        pp = json.loads(row.get("score_points_faibles") or "[]")
                        if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                        if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                    except Exception:
                        pass
 
                    # Description
                    if pd.notna(row.get("description")) and row["description"]:
                        with st.expander("Description complète"):
                            st.markdown(str(row["description"])[:3000], unsafe_allow_html=False)
 
                    st.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True)
                    st.divider()
 
                    # Boutons de décision
                    c_a, c_b, c_c = st.columns(3)
                    btn_top = c_a.button("⭐ Excellent",       key=f"top_{job_key}", use_container_width=True)
                    btn_oui = c_b.button("👍 Intéressant",     key=f"oui_{job_key}", use_container_width=True)
                    btn_non = c_c.button("👎 Pas intéressant", key=f"non_{job_key}", use_container_width=True)
 
                    if btn_top: st.session_state[f"dec_hcl_{job_id}"] = "⭐"
                    if btn_oui: st.session_state[f"dec_hcl_{job_id}"] = "👍"
                    if btn_non: st.session_state[f"dec_hcl_{job_id}"] = "👎"
 
                    if f"dec_hcl_{job_id}" in st.session_state:
                        dec = st.session_state[f"dec_hcl_{job_id}"]
                        st.markdown(f"**Décision : {dec}**")
                        commentaire = st.text_area("Ton feedback :", key=f"comment_{job_key}", height=80)
 
                        if st.button("💾 Sauvegarder", key=f"save_{job_key}", use_container_width=True, type="primary"):
                            with get_connection() as _conn:
                                save_feedback_hcl(_conn, int(job_id), dec, commentaire)
                            del st.session_state[f"dec_hcl_{job_id}"]
                            st.success("✅ Sauvegardé !")
                            st.cache_data.clear()
                            st.rerun()
 
    # ── Onglet : Déjà évalués
    with tab_done:
        if df_deja_evalues.empty:
            st.info("Aucun feedback HCL pour l'instant.")
        else:
            with get_connection() as _conn:
                fb_full = {
                    f["job_id"]: f
                    for f in __import__("database_hcl", fromlist=["get_feedbacks_hcl"]).get_feedbacks_hcl(_conn)
                }
 
            for _, row in df_deja_evalues.iterrows():
                f = fb_full.get(row["id"], {})
                dec = f.get("decision","?")
 
                with st.expander(f"{dec} **{row['title']}** — {row['location']}"):
                    score_val = int(row["score"]) if pd.notna(row.get("score")) else None
                    date_pub = row["first_seen"].strftime("%d/%m/%Y") if pd.notna(row.get("first_seen")) else "–"
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Score",        f"{score_val}/100" if score_val else "–")
                    c2.metric("Contrat",      row.get("contrat","–") or "–")
                    c3.metric("Première vue", date_pub)
 
                    if f.get("commentaire"):
                        st.markdown(f"**Feedback :** {f['commentaire']}")
                    created = str(f.get("created_at",""))[:10]
                    if created:
                        st.caption(f"Évalué le {created}")
 
                    c_link, c_del = st.columns(2)
                    c_link.link_button("🔗 Voir l'offre →", row["url"], use_container_width=True)
                    with c_del:
                        if st.button("🗑️ Supprimer", key=f"del_hcl_{row['id']}", use_container_width=True):
                            with get_connection() as _conn:
                                delete_feedback_hcl(_conn, int(row["id"]))
                            st.cache_data.clear()
                            st.rerun()
 
 
# ══════════════════════════════════════════════════════════════════════════════
# 🚀 À POSTULER — HCL
# ══════════════════════════════════════════════════════════════════════════════
 
elif page == "🚀 À postuler HCL":
    st.title("🚀 À postuler — HCL")
 
    with get_connection() as _conn:
        fb_hcl = get_feedbacks_hcl_simple(_conn)
 
    fb_positifs = {f["job_id"] for f in fb_hcl if f["decision"] in ("⭐", "👍")}
 
    df_postuler = df_active[
        df_active["id"].isin(fb_positifs)
    ].copy()
 
    if df_postuler.empty:
        st.info("Aucune offre à postuler — évalue des offres dans **📝 À évaluer HCL**.")
        st.stop()
 
    df_postuler["score_num"] = pd.to_numeric(df_postuler["score"], errors="coerce")
    df_postuler = df_postuler.sort_values("score_num", ascending=False).reset_index(drop=True)
 
    fb_dec = {f["job_id"]: f["decision"] for f in fb_hcl}
 
    if "selected_job_hcl" not in st.session_state:
        st.session_state.selected_job_hcl = df_postuler.iloc[0]["id"]
 
    col_left, col_right = st.columns([1, 2])
 
    with col_left:
        st.subheader(f"📋 {len(df_postuler)} offres")
        for _, row in df_postuler.iterrows():
            job_id    = row["id"]
            score_val = int(row["score"]) if pd.notna(row.get("score")) else "–"
            dec_emoji = fb_dec.get(job_id, "👍")
            label     = f"{dec_emoji} {row['title'][:32]}… ({score_val}/100)"
            active    = job_id == st.session_state.selected_job_hcl
 
            if st.button(label, key=f"hcl_apply_{job_id}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.selected_job_hcl = job_id
                st.rerun()
 
    with col_right:
        sel = df_postuler[df_postuler["id"] == st.session_state.selected_job_hcl]
        if sel.empty:
            st.info("Sélectionne une offre.")
            st.stop()
 
        job = sel.iloc[0]
 
        st.subheader(job["title"])
        st.markdown(f"📍 **{job['location']}** · 📄 {job.get('contrat','–')}")
 
        score_val = int(job["score"]) if pd.notna(job.get("score")) else "–"
        prio      = job.get("priorite","–")
        emoji     = "🟢" if isinstance(score_val, int) and score_val >= 80 else "🟡" if isinstance(score_val, int) and score_val >= 60 else "🔴"
 
        c1, c2 = st.columns(2)
        c1.metric("Score",    f"{emoji} {score_val}/100" if score_val != "–" else "–")
        c2.metric("Priorité", prio)
 
        if pd.notna(job.get("score_raison")) and job["score_raison"]:
            with st.expander("🧠 Analyse IA"):
                st.write(job["score_raison"])
                try:
                    pf = json.loads(job.get("score_points_forts") or "[]")
                    pp = json.loads(job.get("score_points_faibles") or "[]")
                    if pf: st.markdown("**✅ Points forts :** " + " · ".join(pf))
                    if pp: st.markdown("**⚠️ Points faibles :** " + " · ".join(pp))
                except Exception:
                    pass
 
        if pd.notna(job.get("description")) and job["description"]:
            with st.expander("📄 Description complète"):
                st.markdown(str(job["description"])[:3000], unsafe_allow_html=False)
 
        st.divider()
        st.link_button("🚀 Postuler sur HCL →", job["url"], use_container_width=True, type="primary")



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