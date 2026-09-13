import os
import time
import threading
import requests
from flask import Flask

# =========================
# CONFIGURATION
# =========================

API_KEY = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@goalplus01")

API_BASE = "https://v3.football.api-sports.io"

HEADERS = {
    "x-apisports-key": API_KEY
}

# Grandes compétitions
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

# =========================
# SERVEUR WEB POUR RENDER
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Goal Plus Live is running"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )


# =========================
# TELEGRAM
# =========================

def send_telegram(message):
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN manquant.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "text": message
        },
        timeout=20
    )

    if not response.ok:
        print("❌ Erreur Telegram :", response.text)

    return response.ok


# =========================
# API-FOOTBALL
# =========================

def get_live_matches():
    response = requests.get(
        f"{API_BASE}/fixtures?live=all",
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json().get("response", [])


def get_events(fixture_id):
    response = requests.get(
        f"{API_BASE}/fixtures/events?fixture={fixture_id}",
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json().get("response", [])


# =========================
# CREATION DES PUBLICATIONS
# =========================

def event_message(match, event):

    teams = match["teams"]

    home = teams["home"]["name"]
    away = teams["away"]["name"]

    player = event.get("player", {}).get("name")
    assist = event.get("assist", {}).get("name")

    event_type = event.get("type")
    detail = event.get("detail")

    minute = event.get("time", {}).get("elapsed", "?")

    score_home = match.get("goals", {}).get("home")
    score_away = match.get("goals", {}).get("away")

    score = f"{score_home} - {score_away}"

    # BUT REFUSÉ
    if detail == "Disallowed":
        return (
            f"❌⚽ BUT REFUSÉ\n\n"
            f"{home} {score} {away}\n"
            f"⏱️ {minute}'"
        )

    # PENALTY MANQUÉ
    if detail == "Missed Penalty":
        return (
            f"❌⚽ PENALTY MANQUÉ\n\n"
            f"{home} {score} {away}\n"
            f"⏱️ {minute}'\n"
            f"👤 {player or 'Joueur'}"
        )

    # BUT
    if event_type == "Goal":

        if detail == "Own Goal":
            return (
                f"⚽ BUT CONTRE SON CAMP !\n\n"
                f"{home} {score} {away}\n"
                f"⏱️ {minute}'\n"
                f"👤 {player or 'Joueur'}"
            )

        message = (
            f"⚽ BUT !\n\n"
            f"{home} {score} {away}\n"
            f"⏱️ {minute}'\n"
            f"👤 {player or 'Joueur'}"
        )

        if assist:
            message += f"\n🎯 Passe décisive : {assist}"

        return message

    # CARTONS
    if event_type == "Card":

        if detail == "Yellow Card":
            icon = "🟨"
            title = "CARTON JAUNE"

        elif detail in ["Red Card", "Second Yellow card"]:
            icon = "🟥"
            title = "CARTON ROUGE"

        else:
            return None

        return (
            f"{icon} {title}\n\n"
            f"{home} {score} {away}\n"
            f"⏱️ {minute}'\n"
            f"👤 {player or 'Joueur'}"
        )

    # REMPLACEMENT
    if event_type == "subst":

        entrant = event.get("assist", {}).get("name")
        sortant = player

        return (
            f"🔄 CHANGEMENT\n\n"
            f"{home} {score} {away}\n"
            f"⏱️ {minute}'\n"
            f"⬆️ {entrant or 'Entrant'}\n"
            f"⬇️ {sortant or 'Sortant'}"
        )

    return None


# =========================
# SURVEILLANCE
# =========================

def monitor():

    if not API_KEY:
        print("❌ API_FOOTBALL_KEY manquante.")
        return

    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN manquant.")
        return

    print("🟢 GOAL PLUS LIVE — BOT DÉMARRÉ")

    while True:

        try:

            matches = get_live_matches()

            print(
                f"🔎 {len(matches)} matchs en direct analysés."
            )

            for match in matches:

                league = match.get("league", {})

                competition = (
                    league.get("name"),
                    league.get("country")
                )

                # Filtre compétitions
                if competition not in COMPETITIONS:
                    continue

                fixture_id = match["fixture"]["id"]

                print(
                    f"⚽ Match surveillé : "
                    f"{match['teams']['home']['name']} "
                    f"vs "
                    f"{match['teams']['away']['name']}"
                )

                # Récupération des événements
                events = get_events(fixture_id)

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

                    message = event_message(
                        match,
                        event
                    )

                    if message:

                        if send_telegram(message):

                            seen_events.add(event_id)

                            print(
                                "📨 Publication :",
                                message
                            )

                # STATUT DU MATCH
                status = match["fixture"]["status"]["short"]

                status_id = (
                    fixture_id,
                    status
                )

                home = match["teams"]["home"]["name"]
                away = match["teams"]["away"]["name"]

                home_score = match["goals"]["home"]
                away_score = match["goals"]["away"]

                # MI-TEMPS
                if (
                    status == "HT"
                    and status_id not in seen_status
                ):

                    send_telegram(
                        f"⏸️ MI-TEMPS\n\n"
                        f"{home} {home_score} - "
                        f"{away_score} {away}"
                    )

                    seen_status.add(status_id)

                # FIN DU MATCH
                if (
                    status in ["FT", "AET", "PEN"]
                    and status_id not in seen_status
                ):

                    send_telegram(
                        f"🏁 FIN DU MATCH\n\n"
                        f"{home} {home_score} - "
                        f"{away_score} {away}"
                    )

                    seen_status.add(status_id)

            print(
                "💤 Prochaine vérification dans 15 minutes..."
            )

            time.sleep(900)

        except Exception as error:

            print(
                "⚠️ Erreur :",
                error
            )

            time.sleep(60)


# =========================
# DÉMARRAGE
# =========================

if __name__ == "__main__":

    # Flask démarre immédiatement
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    # Bot de surveillance
    monitor()
