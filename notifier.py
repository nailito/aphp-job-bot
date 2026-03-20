# ============================================================
#  notifier.py  —  Envoi du rapport par email (HTML)
# ============================================================
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_SERVER, SMTP_PORT


def _score_color(score: int) -> str:
    if score >= 8: return "#16a34a"   # vert
    if score >= 6: return "#d97706"   # orange
    return "#dc2626"                   # rouge


def _score_emoji(score: int) -> str:
    if score >= 8: return "🟢"
    if score >= 6: return "🟡"
    return "🔴"


def build_html_report(jobs: list[dict]) -> str:
    """Génère un email HTML propre avec toutes les offres."""
    date_str = datetime.now().strftime("%d/%m/%Y")
    count    = len(jobs)

    cards = ""
    for job in jobs:
        score    = job.get("score", 0)
        color    = _score_color(score)
        emoji    = _score_emoji(score)
        pf_html  = "".join(f"<li>✅ {p}</li>" for p in job.get("points_forts", []))
        pp_html  = "".join(f"<li>⚠️ {p}</li>" for p in job.get("points_faibles", []))

        cards += f"""
        <div style="border:1px solid #e5e7eb; border-radius:12px; padding:20px;
                    margin-bottom:20px; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.05)">
          <div style="display:flex; justify-content:space-between; align-items:flex-start">
            <div style="flex:1">
              <h2 style="margin:0 0 4px; font-size:17px; color:#111827">
                <a href="{job.get('url','#')}" style="color:#1d4ed8; text-decoration:none">
                  {job.get('title','Sans titre')}
                </a>
              </h2>
              <p style="margin:0; color:#6b7280; font-size:13px">
                📍 {job.get('location','Non précisé')}
              </p>
            </div>
            <div style="text-align:center; min-width:60px; margin-left:16px">
              <span style="font-size:28px">{emoji}</span>
              <div style="font-size:22px; font-weight:700; color:{color}">{score}/10</div>
            </div>
          </div>

          <p style="margin:12px 0 8px; font-style:italic; color:#374151">
            {job.get('resume','')}
          </p>

          <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:10px">
            <div>
              <strong style="font-size:13px; color:#059669">Points forts</strong>
              <ul style="margin:4px 0; padding-left:18px; font-size:13px; color:#374151">{pf_html}</ul>
            </div>
            <div>
              <strong style="font-size:13px; color:#d97706">Points d'attention</strong>
              <ul style="margin:4px 0; padding-left:18px; font-size:13px; color:#374151">{pp_html}</ul>
            </div>
          </div>

          <p style="margin:10px 0 0; font-size:13px; color:#4b5563; background:#f9fafb;
                    border-radius:6px; padding:10px">
            💬 <em>{job.get('verdict','')}</em>
          </p>

          <a href="{job.get('url','#')}"
             style="display:inline-block; margin-top:14px; padding:8px 18px;
                    background:#1d4ed8; color:#fff; border-radius:8px;
                    text-decoration:none; font-size:13px; font-weight:600">
            Voir l'offre →
          </a>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="UTF-8">
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              background:#f3f4f6; margin:0; padding:0 }}
    </style>
    </head>
    <body>
      <div style="max-width:680px; margin:30px auto; padding:0 16px">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#1d4ed8,#7c3aed); border-radius:16px;
                    padding:28px; color:#fff; margin-bottom:24px">
          <h1 style="margin:0 0 6px; font-size:22px">🏥 Veille APHP — {date_str}</h1>
          <p style="margin:0; opacity:.85">{count} offre(s) sélectionnée(s) pour ton profil</p>
        </div>

        {cards if cards else '<p style="text-align:center;color:#6b7280">Aucune offre pertinente aujourd\'hui.</p>'}

        <!-- Footer -->
        <p style="text-align:center; color:#9ca3af; font-size:12px; margin-top:24px">
          Bot de veille APHP · Propulsé par Claude (Anthropic)
        </p>
      </div>
    </body>
    </html>
    """
    return html


def send_email(jobs: list[dict]) -> None:
    """Envoie le rapport par email."""
    if not jobs:
        subject = f"[APHP Bot] Aucune nouvelle offre pertinente — {datetime.now().strftime('%d/%m/%Y')}"
        html    = "<p>Aucune offre correspondant à ton profil aujourd'hui. À demain !</p>"
    else:
        subject = f"[APHP Bot] {len(jobs)} offre(s) pour toi — {datetime.now().strftime('%d/%m/%Y')}"
        html    = build_html_report(jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"\n📧 Envoi de l'email à {EMAIL_RECIPIENT}...")
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print("✅ Email envoyé !")
    except Exception as e:
        print(f"❌ Erreur d'envoi : {e}")
        raise
