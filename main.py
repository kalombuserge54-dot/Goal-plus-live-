import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Goal Plus Live is running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

API_KEY = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@goalplus01")

HEADERS = {
    "x-apisports-key": API_KEY
}

LIVE_URL = "https://v3.football.api-sports.io/fixtures?live=all"

# Grandes compétitions uniquement
COMPETITIONS = {
    ("Premier League", "England"),
    ("La Liga", "Spain"),
    ("Serie A", "Italy"),
    ("Bundesliga", "Germany"),
    ("Ligue 1", "France"),
    ("UEFA Champions League", "World"),
    ("UEFA Europa League", "World"),
}

seen_events = set()
seen_status = set()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "text": message
        },
        timeout=20
    )

    return response.ok


def get_live_matches():
    response = requests.get(
        LIVE_URL,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()
    return response.json().get("response", [])


def event_message(match, event):
    teams = match["teams"]
    home = teams["home"]["name"]
    away = teams["away"]["name"]

    player = event.get("player", {}).get("name")
    assist = event.get("assist", {}).get("name")
    event_type = event.get("type")
    detail = event.get("detail")

    minute = event.get("time", {}).get("elapsed", "?")

    if detail == "Disallowed":
        return f"❌⚽ BUT REFUSÉ\n\n{home} {minute}' {away}"

    if detail == "Missed Penalty":
        return f"❌⚽ PENALTY MANQUÉ\n\n{home} {minute}' {away}\n👤 {player or 'Joueur'}"

    if event_type == "Goal":
        if detail == "Own Goal":
            return (
                f"⚽ BUT CONTRE SON CAMP !\n\n"
                f"{home} {minute}' {away}\n"
                f"👤 {player or 'Joueur'}"
            )

        text = (
            f"⚽ BUT !\n\n"
            f"{home} {minute}' {away}\n"
            f"👤 {player or 'Joueur'}"
        )

        if assist:
            text += f"\n🎯 Passe décisive : {assist}"

        return text

    if event_type == "Card":
        if detail == "Yellow Card":
            icon = "🟨"
        elif detail in ["Red Card", "Second Yellow card"]:
            icon = "🟥"
        else:
            return None

        return (
            f"{icon} CARTON !\n\n"
            f"{home} {minute}' {away}\n"
            f"👤 {player or 'Joueur'}"
        )

    if event_type == "subst":
        return (
            f"🔄 CHANGEMENT\n\n"
            f"{home} {minute}' {away}\n"
            f"⬆️ {event.get('assist', {}).get('name') or 'Entrant'}\n"
            f"⬇️ {player or 'Sortant'}"
        )

    return None


def main():
    if not API_KEY or not BOT_TOKEN:
        print("❌ Variables d'environnement manquantes.")
        return

    print("🟢 GOAL PLUS LIVE — BOT DÉMARRÉ")

    while True:
        try:
            matches = get_live_matches()

            print(f"🔎 {len(matches)} matchs en direct analysés.")

            for match in matches:
                league = match["league"]

                competition = (
                    league["name"],
                    league["country"]
                )

                if competition not in COMPETITIONS:
                    continue

                fixture_id = match["fixture"]["id"]
                events_url = (
                    f"https://v3.football.api-sports.io/"
                    f"fixtures/events?fixture={fixture_id}"
                )

                response = requests.get(
                    events_url,
                    headers=HEADERS,
                    timeout=20
                )

                events = response.json().get("response", [])

                for event in events:
                    event_id = (
                        fixture_id,
                        event.get("time", {}).get("elapsed"),
                        event.get("type"),
                        event.get("detail"),
                        event.get("player", {}).get("id")
                    )

                    if event_id in seen_events:
                        continue

                    message = event_message(match, event)

                    if message:
                        if send_telegram(message):
                            seen_events.add(event_id)
                            print("📨 Publication :", message)

                status = match["fixture"]["status"]["short"]

                status_id = (fixture_id, status)

                if status == "HT" and status_id not in seen_status:
                    send_telegram(
                        f"⏸️ MI-TEMPS\n\n"
                        f"{match['teams']['home']['name']} "
                        f"{match['goals']['home']} - "
                        f"{match['goals']['away']} "
                        f"{match['teams']['away']['name']}"
                    )
                    seen_status.add(status_id)

            print("💤 Prochaine vérification dans 15 minutes...")
            time.sleep(900)

        except Exception as error:
            print("⚠️ Erreur :", error)
            time.sleep(60)


if __name__ == "__main__":
    main()
