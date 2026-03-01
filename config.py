"""
config.py – centralna konfiguracja projektu.
Wszystkie moduły importują stałe, logger i engine stąd, a nie z main.py.
"""
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

# ---------------------------------------------------------------------------
# Zmienne środowiskowe
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Logowanie
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('football_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
API_KEY  = os.getenv('API_KEY')
BASE_URL = os.getenv('BASE_URL', 'https://v3.football.api-sports.io')
SEASON   = int(os.getenv('SEASON', '2025'))

HEADERS = {
    'x-rapidapi-host': 'v3.football.api-sports.io',
    'x-rapidapi-key': API_KEY
}

# ---------------------------------------------------------------------------
# Baza danych
# ---------------------------------------------------------------------------
DB_USER     = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST     = os.getenv('DB_HOST', 'localhost')
DB_PORT     = os.getenv('DB_PORT', '5433')
DB_NAME     = os.getenv('DB_NAME')

if not all([API_KEY, DB_USER, DB_PASSWORD, DB_NAME]):
    logger.error("Brak wymaganych zmiennych środowiskowych. Sprawdź plik .env")
    raise ValueError("Brak wymaganych zmiennych środowiskowych w pliku .env")

DB_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(DB_URL)

# ---------------------------------------------------------------------------
# Ligi
# ---------------------------------------------------------------------------
TOP_20_LEAGUES = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    88:  "Eredivisie",
    94:  "Primeira Liga",
    71:  "Serie A (Brazil)",
    128: "Liga Profesional (Argentina)",
    203: "Süper Lig",
    144: "Jupiler Pro League",
    253: "Major League Soccer",
    307: "Saudi Pro League",
    40:  "Championship",
    106: "Ekstraklasa",
    179: "Premiership (Scotland)",
    197: "Super League (Greece)",
    262: "Liga MX",
    218: "Bundesliga (Austria)",
    207: "Super League (Switzerland)",
}
