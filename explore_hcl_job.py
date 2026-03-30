"""
explore_hcl.py
Dashboard d'exploration temporaire des offres HCL.
Fetch direct depuis l'API REST WP — aucune base de données requise.

Lancement : streamlit run explore_hcl.py
"""

import collections
import json
import os
import time
from html import unescape

import pandas as pd
import psycopg2
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config page
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="HCL · Exploration des offres",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS custom
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ── Palette ── */
:root {
    --bg:        #0f1117;
    --surface:   #1a1d27;
    --surface2:  #222538;
    --border:    #2e3250;
    --accent:    #4f7cff;
    --accent2:   #7c5cfc;
    --green:     #22c55e;
    --orange:    #f59e0b;
    --red:       #ef4444;
    --muted:     #6b7280;
    --text:      #e2e8f0;
    --text-dim:  #94a3b8;
}

/* ── Global ── */
.stApp { background: var(--bg); color: var(--text); }
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
div[data-testid="stSidebarContent"] { padding-top: 1rem; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── KPI cards ── */
.kpi-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.kpi-card {
    flex: 1; min-width: 140px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.kpi-card .kpi-value {
    font-size: 2rem; font-weight: 800; letter-spacing: -1px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    line-height: 1;
}
.kpi-card .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-top: 0.3rem; }

/* ── Section title ── */
.section-title {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: var(--muted);
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem; margin: 1.25rem 0 0.75rem;
}

/* ── Offer card ── */
.offer-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.85rem;
    transition: border-color .2s;
    position: relative;
}
.offer-card:hover { border-color: var(--accent); }
.offer-card .offer-id {
    position: absolute; top: 1rem; right: 1.25rem;
    font-size: 0.65rem; color: var(--muted); font-family: monospace;
}
.offer-title {
    font-size: 1rem; font-weight: 700; color: var(--text);
    line-height: 1.3; margin-bottom: 0.6rem; padding-right: 3rem;
}
.offer-title a { color: var(--text); text-decoration: none; }
.offer-title a:hover { color: var(--accent); }

/* ── Badges ── */
.badges { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
.badge {
    font-size: 0.68rem; font-weight: 600; padding: 0.2rem 0.6rem;
    border-radius: 999px; white-space: nowrap;
}
.badge-contrat { background: rgba(79,124,255,.15); color: #7aa3ff; border: 1px solid rgba(79,124,255,.3); }
.badge-hopital { background: rgba(124,92,252,.15); color: #a78bfa; border: 1px solid rgba(124,92,252,.3); }
.badge-filiere { background: rgba(34,197,94,.12); color: #4ade80; border: 1px solid rgba(34,197,94,.25); }
.badge-duree   { background: rgba(245,158,11,.12); color: #fbbf24; border: 1px solid rgba(245,158,11,.25); }
.badge-date    { background: rgba(148,163,184,.1); color: var(--text-dim); border: 1px solid var(--border); }

/* ── Description preview ── */
.desc-preview {
    font-size: 0.82rem; color: var(--text-dim); line-height: 1.6;
    border-left: 2px solid var(--border);
    padding-left: 0.75rem; margin-top: 0.5rem;
    white-space: pre-wrap;
}
.desc-full {
    font-size: 0.8rem; color: var(--text-dim); line-height: 1.7;
    background: var(--surface2); border-radius: 8px;
    padding: 1rem; margin-top: 0.5rem;
    white-space: pre-wrap; max-height: 500px; overflow-y: auto;
    border: 1px solid var(--border);
}

/* ── Search bar ── */
.stTextInput input {
    background: var(--surface2) !important; border: 1px solid var(--border) !important;
    color: var(--text) !important; border-radius: 10px !important;
}

/* ── Multiselect ── */
.stMultiSelect [data-baseweb="tag"] { background: var(--accent) !important; }

/* ── Expander ── */
.streamlit-expanderHeader {
    font-size: 0.78rem !important; color: var(--accent) !important;
    background: transparent !important;
}

/* ── Horizontal rule ── */
hr { border-color: var(--border); margin: 0.5rem 0; }

/* ── Sidebar labels ── */
.stSidebar label { font-size: 0.75rem !important; color: var(--text-dim) !important; }

/* ── Raw JSON block ── */
.raw-json { font-size: 0.7rem; font-family: monospace; color: var(--muted);
    background: var(--surface2); border-radius: 8px; padding: 0.75rem;
    overflow-x: auto; white-space: pre; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constantes API
# ---------------------------------------------------------------------------

API_BASE = "https://chu-lyon.nous-recrutons.fr/wp-json/wp/v2"
JOB_URL  = f"{API_BASE}/job"
PER_PAGE = 100
HEADERS  = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

TAXONOMY_SLUGS = {
    "contrats":    "job_custom_chulyon_typedecontrat",
    "hopital":     "job_custom_hcl_hopital",
    "filiere":     "job_custom_hcl_filiere",
    "contrat_alt": "job_contract_type",
}

# ---------------------------------------------------------------------------
# Fonctions de fetch (avec cache Streamlit)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all_raw() -> list[dict]:
    """Pagine l'API et retourne tous les objets JSON bruts."""
    session = requests.Session()
    all_raw, page = [], 1
    while True:
        resp = session.get(JOB_URL, params={
            "per_page": PER_PAGE, "page": page,
            "order": "desc", "orderby": "date",
        }, headers=HEADERS, timeout=30)
        if resp.status_code in (400, 404):
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_raw.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
        time.sleep(0.2)
    return all_raw


# FIX : charge les décisions IA depuis la DB (sans dépendre de database_hcl)
@st.cache_data(ttl=300)
def load_filter_results() -> dict:
    try:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            return {}
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("SELECT id, ai_filter_decision FROM hcl_jobs")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {row[0]: row[1] for row in rows} if rows else {}
    except Exception as e:
        st.warning(f"Impossible de charger les décisions IA : {e}")
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_taxonomy_labels(taxonomy: str) -> dict[int, str]:
    """Retourne {term_id: label} pour une taxonomie donnée."""
    session = requests.Session()
    labels, page = {}, 1
    while True:
        try:
            resp = session.get(f"{API_BASE}/{taxonomy}", params={
                "per_page": 100, "page": page,
            }, headers=HEADERS, timeout=15)
            if resp.status_code in (400, 404):
                break
            resp.raise_for_status()
            terms = resp.json()
            if not terms:
                break
            for t in terms:
                if isinstance(t, dict) and "id" in t:
                    labels[t["id"]] = unescape(t.get("name", str(t["id"]))).strip()
            if len(terms) < 100:
                break
            page += 1
        except Exception:
            break
    return labels


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["br", "p", "li", "h1", "h2", "h3", "h4"]):
        tag.insert_before("\n")
    lines = [l.strip() for l in soup.get_text(" ").splitlines() if l.strip()]
    return "\n".join(lines)


def resolve_ids(ids: list, labels: dict) -> list[str]:
    return [labels.get(i, str(i)) for i in (ids or [])]


def build_description(raw: dict) -> str:
    parts = []
    content = html_to_text(raw.get("content", {}).get("rendered", ""))
    if content:
        parts.append(content)
    meta = raw.get("meta") or {}
    for key, label in [("job_offer_mission", "Mission"), ("job_offer_profile", "Profil recherché")]:
        val = str(meta.get(key) or "").strip()
        if val and val != "0":
            parts.append(f"{label} :\n{html_to_text(val)}")
    return "\n\n".join(parts).strip()


@st.cache_data(ttl=1800, show_spinner=False)
def load_offers() -> list[dict]:
    """Charge et normalise toutes les offres depuis l'API."""
    raw_list = fetch_all_raw()

    tax_labels = {
        slug: fetch_taxonomy_labels(slug)
        for slug in TAXONOMY_SLUGS.values()
    }

    offers = []
    for raw in raw_list:
        meta = raw.get("meta") or {}

        contrat_ids = raw.get(TAXONOMY_SLUGS["contrats"]) or raw.get(TAXONOMY_SLUGS["contrat_alt"]) or []
        hopital_ids = raw.get(TAXONOMY_SLUGS["hopital"]) or []
        filiere_ids = raw.get(TAXONOMY_SLUGS["filiere"]) or []

        contrats = resolve_ids(contrat_ids, tax_labels[TAXONOMY_SLUGS["contrats"]])
        hopitaux = resolve_ids(hopital_ids, tax_labels[TAXONOMY_SLUGS["hopital"]])
        filieres = resolve_ids(filiere_ids, tax_labels[TAXONOMY_SLUGS["filiere"]])

        duree      = str(meta.get("job_offer_duration") or "").strip()
        date_debut = str(meta.get("job_creation_date") or "").strip()
        date_pub   = raw.get("date", "")[:10] if raw.get("date") else ""

        description = build_description(raw)

        offers.append({
            "id":          raw["id"],
            "titre":       html_to_text(raw.get("title", {}).get("rendered", "")).strip(),
            "url":         raw.get("link", ""),
            "contrats":    contrats,
            "hopitaux":    hopitaux,
            "filieres":    filieres,
            "duree":       duree if duree and duree != "0" else "",
            "date_debut":  date_debut if date_debut and date_debut != "0" else "",
            "date_pub":    date_pub,
            "description": description,
            "_raw":        raw,
        })

    return offers


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------

with st.spinner("⏳ Chargement des offres HCL depuis l'API…"):
    offers = load_offers()
    filter_map = load_filter_results()

# FIX : injecter la décision IA dans chaque offre (pas de conn/get_active_offers)
for o in offers:
    o["ai_filter_decision"] = filter_map.get(o["id"])

# ---------------------------------------------------------------------------
# Sidebar — filtres
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🏥 HCL · Explorer")

    only_validated = st.checkbox("Seulement validées par IA", value=False)

    st.markdown(
        f"<div style='color:#6b7280;font-size:.75rem;margin-bottom:1rem'>"
        f"{len(offers)} offres chargées · cache 30min</div>",
        unsafe_allow_html=True,
    )

    if st.button("🔄 Rafraîchir les données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown('<div class="section-title">Recherche</div>', unsafe_allow_html=True)
    search = st.text_input("", placeholder="Titre, description…", label_visibility="collapsed")

    st.markdown('<div class="section-title">Filtres</div>', unsafe_allow_html=True)

    all_contrats = sorted({c for o in offers for c in o["contrats"]})
    all_hopitaux = sorted({h for o in offers for h in o["hopitaux"]})
    all_filieres = sorted({f for o in offers for f in o["filieres"]})

    sel_contrats = st.multiselect("Type de contrat", all_contrats)
    sel_hopitaux = st.multiselect("Hôpital / site", all_hopitaux)
    sel_filieres = st.multiselect("Filière métier", all_filieres)

    st.divider()
    st.markdown('<div class="section-title">Description</div>', unsafe_allow_html=True)
    has_desc = st.checkbox("Avec description uniquement", value=False)

    st.divider()
    st.markdown('<div class="section-title">Affichage</div>', unsafe_allow_html=True)
    show_raw  = st.checkbox("Afficher le JSON brut", value=False)
    desc_mode = st.radio("Description", ["Aperçu (3 lignes)", "Complète", "Masquée"], horizontal=False)
    per_page_ui = st.select_slider("Offres par page", options=[10, 25, 50, 100], value=25)

# ---------------------------------------------------------------------------
# Filtrage — FIX : search intégré dans matches()
# ---------------------------------------------------------------------------

def matches(offer: dict) -> bool:
    if only_validated and offer.get("ai_filter_decision") != "pass":
        return False
    if sel_contrats and not any(c in offer["contrats"] for c in sel_contrats):
        return False
    if sel_hopitaux and not any(h in offer["hopitaux"] for h in sel_hopitaux):
        return False
    if sel_filieres and not any(f in offer["filieres"] for f in sel_filieres):
        return False
    if has_desc and not offer["description"].strip():
        return False
    # FIX : appliquer la recherche texte
    if search:
        q = search.lower()
        if q not in offer["titre"].lower() and q not in offer["description"].lower():
            return False
    return True

filtered = [o for o in offers if matches(o)]

# ---------------------------------------------------------------------------
# Header + KPI
# ---------------------------------------------------------------------------

st.markdown("## Exploration des offres HCL")

contrats_set = {c for o in offers for c in o["contrats"]}
hopitaux_set = {h for o in offers for h in o["hopitaux"]}
filieres_set = {f for o in offers for f in o["filieres"]}
with_desc    = sum(1 for o in offers if o["description"].strip())

st.markdown(f"""
<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-value">{len(offers)}</div>
    <div class="kpi-label">Offres totales</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{len(filtered)}</div>
    <div class="kpi-label">Après filtres</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{len(hopitaux_set)}</div>
    <div class="kpi-label">Hôpitaux / sites</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{len(filieres_set)}</div>
    <div class="kpi-label">Filières</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{len(contrats_set)}</div>
    <div class="kpi-label">Types contrat</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{with_desc}</div>
    <div class="kpi-label">Avec description</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Stats rapides (charts)
# ---------------------------------------------------------------------------

with st.expander("📊 Distributions", expanded=False):
    col1, col2, col3 = st.columns(3)

    cnt_contrat = collections.Counter(c for o in filtered for c in (o["contrats"] or ["Non précisé"]))
    cnt_fil     = collections.Counter(f for o in filtered for f in (o["filieres"] or ["Non précisé"]))
    cnt_hop     = collections.Counter(h for o in filtered for h in (o["hopitaux"] or ["Non précisé"]))

    with col1:
        st.markdown("**Par type de contrat**")
        if cnt_contrat:
            df_c = pd.DataFrame(cnt_contrat.most_common(15), columns=["Contrat", "Nb"])
            st.bar_chart(df_c.set_index("Contrat"), use_container_width=True, height=250)

    with col2:
        st.markdown("**Par filière (top 15)**")
        if cnt_fil:
            df_f = pd.DataFrame(cnt_fil.most_common(15), columns=["Filière", "Nb"])
            st.bar_chart(df_f.set_index("Filière"), use_container_width=True, height=250)

    with col3:
        st.markdown("**Par hôpital (top 15)**")
        if cnt_hop:
            df_h = pd.DataFrame(cnt_hop.most_common(15), columns=["Hôpital", "Nb"])
            st.bar_chart(df_h.set_index("Hôpital"), use_container_width=True, height=250)

    st.markdown("---")
    st.markdown("**Toutes les valeurs disponibles**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("*Contrats*")
        for v, n in cnt_contrat.most_common():
            st.markdown(f"`{v}` — {n}")
    with c2:
        st.markdown("*Filières*")
        for v, n in cnt_fil.most_common():
            st.markdown(f"`{v}` — {n}")
    with c3:
        st.markdown("*Hôpitaux*")
        for v, n in cnt_hop.most_common():
            st.markdown(f"`{v}` — {n}")

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

st.markdown(
    f"<div style='color:#6b7280;font-size:.8rem;margin:.5rem 0'>{len(filtered)} offres</div>",
    unsafe_allow_html=True,
)

n_pages = max(1, (len(filtered) + per_page_ui - 1) // per_page_ui)
page_num = st.number_input("Page", min_value=1, max_value=n_pages, value=1, step=1, label_visibility="collapsed") if n_pages > 1 else 1

page_offers = filtered[(page_num - 1) * per_page_ui : page_num * per_page_ui]

if not page_offers:
    st.info("Aucune offre ne correspond aux filtres sélectionnés.")

# ---------------------------------------------------------------------------
# Rendu des cartes
# ---------------------------------------------------------------------------

def render_badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{text}</span>'

for offer in page_offers:
    badges_html = '<div class="badges">'
    for c in offer["contrats"]:
        badges_html += render_badge(c, "badge-contrat")
    for h in offer["hopitaux"]:
        badges_html += render_badge(h, "badge-hopital")
    for f in offer["filieres"]:
        badges_html += render_badge(f, "badge-filiere")
    if offer["duree"]:
        badges_html += render_badge(f"⏱ {offer['duree']}", "badge-duree")
    if offer["date_pub"]:
        badges_html += render_badge(f"📅 {offer['date_pub']}", "badge-date")
    if offer["date_debut"] and offer["date_debut"] != "0":
        badges_html += render_badge(f"🚀 Début: {offer['date_debut']}", "badge-date")
    if offer.get("ai_filter_decision") == "pass":
        badges_html += render_badge("✅ IA OK", "badge-filiere")
    elif offer.get("ai_filter_decision") == "reject":
        badges_html += render_badge("❌ IA NO", "badge-duree")
    badges_html += '</div>'

    desc = offer["description"]
    if desc_mode == "Aperçu (3 lignes)":
        preview_lines = [l for l in desc.splitlines() if l.strip()][:3]
        preview = "\n".join(preview_lines)
        desc_html = f'<div class="desc-preview">{preview}{"…" if len(preview_lines) == 3 else ""}</div>' if preview else ""
    elif desc_mode == "Complète":
        desc_html = f'<div class="desc-full">{desc}</div>' if desc else '<div class="desc-preview"><em>Pas de description</em></div>'
    else:
        desc_html = ""

    st.markdown(f"""
<div class="offer-card">
  <div class="offer-id">#{offer['id']}</div>
  <div class="offer-title">
    <a href="{offer['url']}" target="_blank">{offer['titre']}</a>
  </div>
  {badges_html}
  {desc_html}
</div>
""", unsafe_allow_html=True)

    if desc_mode == "Aperçu (3 lignes)" and desc:
        with st.expander("📄 Description complète"):
            st.markdown(f'<div class="desc-full">{desc}</div>', unsafe_allow_html=True)

    if show_raw:
        with st.expander(f"🔧 JSON brut #{offer['id']}"):
            raw_display = {k: v for k, v in offer["_raw"].items() if k != "_raw"}
            st.markdown(f'<div class="raw-json">{json.dumps(raw_display, ensure_ascii=False, indent=2)}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Footer pagination
# ---------------------------------------------------------------------------

if n_pages > 1:
    st.markdown(
        f"<div style='text-align:center;color:#6b7280;font-size:.8rem;margin-top:1rem'>Page {page_num} / {n_pages}</div>",
        unsafe_allow_html=True,
    )