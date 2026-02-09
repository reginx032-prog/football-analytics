import requests
import pandas as pd
from sqlalchemy import create_engine
import time

# --- KONFIGURACJA ---
API_KEY = '01ef261cc11abff4b6be19b3403e83f5'
BASE_URL = "https://v3.football.api-sports.io"
DB_URL = 'postgresql://admin:secret_password@localhost:5433/football_data'
SEASON = 2025

HEADERS = {
    'x-rapidapi-host': 'v3.football.api-sports.io',
    'x-rapidapi-key': API_KEY
}

# Słownik mapujący ID na Nazwy Ligi (Opcja A)
TOP_20_LEAGUES = {
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
    88: "Eredivisie",
    94: "Primeira Liga",
    71: "Serie A (Brazil)",
    128: "Liga Profesional (Argentina)",
    203: "Süper Lig",
    144: "Jupiler Pro League",
    253: "Major League Soccer",
    307: "Saudi Pro League",
    40: "Championship",
    106: "Ekstraklasa",
    179: "Premiership (Scotland)",
    197: "Super League (Greece)",
    262: "Liga MX",
    218: "Bundesliga (Austria)",
    207: "Super League (Switzerland)"
}

engine = create_engine(DB_URL)


def fetch_teams(league_id, league_name):
    print(f" Pobieranie danych dla ligi: {league_name} (ID: {league_id})...")
    params = {'league': league_id, 'season': SEASON}

    try:
        response = requests.get(f"{BASE_URL}/teams", headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()

        if not data['response']:
            print(f" Brak danych dla ligi {league_name} w sezonie {SEASON}")
            return None

        teams_list = []
        for item in data['response']:
            t = item['team']
            v = item['venue']

            teams_list.append({
                'team_id': t['id'],
                'name': t['name'],
                'code': t['code'],
                'country': t['country'],
                'founded': t['founded'],
                'stadium_name': v['name'],
                'stadium_city': v['city'],
                'league_id': league_id,
                'league_name': league_name  # Tutaj używamy nazwy ze słownika
            })
        return pd.DataFrame(teams_list)

    except Exception as e:
        print(f" Błąd przy lidze {league_name}: {e}")
        return None


def main():
    all_teams_df = pd.DataFrame()

    # Iterujemy po słowniku (klucz: ID, wartość: Nazwa)
    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_teams(l_id, l_name)
        if df is not None:
            all_teams_df = pd.concat([all_teams_df, df], ignore_index=True)

        # Zachowaj odstęp, by nie przekroczyć limitów API
        time.sleep(2)

    if not all_teams_df.empty:
        print("\n Trwa zapisywanie danych do PostgreSQL...")
        # Zapis do tabeli 'teams'
        all_teams_df.to_sql('teams', engine, if_exists='replace', index=False)
        print(" Sukces! Dane zostały zapisane.")
        print(f" Łącznie pobrano {len(all_teams_df)} drużyn z {len(TOP_20_LEAGUES)} lig.")
    else:
        print(" Nie pobrano żadnych danych.")


if __name__ == "__main__":
    main()