import requests
import os

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MAX_LENGTH = 4000  # Telegram limite à 4096

def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return

    if len(message) > MAX_LENGTH:
        message = message[:MAX_LENGTH] + "…"

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        if not r.ok:
            print(f"⚠️ Telegram HTTP {r.status_code} : {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram erreur : {e}")


def send_telegram_alert(message: str):
    token   = os.getenv("TELEGRAM_TOKEN_ALERT", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_ALERT", "")
    if not token or not chat_id:
        print("(Telegram alert: credentials manquants)")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"(Telegram alert failed: {e})")