import requests
import pandas as pd
from sqlalchemy import create_engine
import time
import logging
import os
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# --- KONFIGURACJA LOGOWANIA ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('football_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- KONFIGURACJA ---
API_KEY = os.getenv('API_KEY')
BASE_URL = os.getenv('BASE_URL', 'https://v3.football.api-sports.io')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5433')
DB_NAME = os.getenv('DB_NAME')
SEASON = int(os.getenv('SEASON', '2025'))

# Walidacja wymaganych zmiennych środowiskowych
if not all([API_KEY, DB_USER, DB_PASSWORD, DB_NAME]):
    logger.error("Brak wymaganych zmiennych środowiskowych. Sprawdź plik .env")
    raise ValueError("Brak wymaganych zmiennych środowiskowych w pliku .env")

DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

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
    logger.info(f"Pobieranie danych dla ligi: {league_name} (ID: {league_id})...")
    params = {'league': league_id, 'season': SEASON}

    try:
        response = requests.get(f"{BASE_URL}/teams", headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get('response'):
            logger.warning(f"Brak danych dla ligi {league_name} w sezonie {SEASON}")
            return None

        teams_list = []
        for item in data['response']:
            t = item.get('team', {})
            v = item.get('venue', {})

            teams_list.append({
                'team_id': t.get('id'),
                'name': t.get('name'),
                'code': t.get('code'),
                'country': t.get('country'),
                'founded': t.get('founded'),
                'stadium_name': v.get('name'),
                'stadium_city': v.get('city'),
                'league_id': league_id,
                'league_name': league_name
            })
        return pd.DataFrame(teams_list)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu danych dla ligi {league_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd żądania HTTP dla ligi {league_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd przy lidze {league_name}: {e}", exc_info=True)
        return None


def main():
    all_teams_df = pd.DataFrame()

    # Iterujemy po słowniku (klucz: ID, wartość: Nazwa)
    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_teams(l_id, l_name)
        if df is not None and not df.empty:
            all_teams_df = pd.concat([all_teams_df, df], ignore_index=True)

        # Zachowaj odstęp, by nie przekroczyć limitów API (Rate limiting)
        time.sleep(2)

    if not all_teams_df.empty:
        logger.info("Trwa zapisywanie danych do PostgreSQL...")
        try:
            all_teams_df.to_sql('teams', engine, if_exists='replace', index=False)
            logger.info("Sukces! Dane zostały zapisane.")
            logger.info(f"Łącznie pobrano {len(all_teams_df)} drużyn z {len(TOP_20_LEAGUES)} lig.")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu do bazy danych: {e}", exc_info=True)
    else:
        logger.warning("Nie pobrano żadnych danych.")


if __name__ == "__main__":
    main()