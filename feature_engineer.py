import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# --- KONFIGURACJA ---
try:
    from main import DB_URL
except ImportError:
    print("❌ Błąd: Brak pliku main.py lub zmiennej DB_URL.")
    exit()

# Połączenie z bazą
engine = create_engine(DB_URL)


def load_and_sort_data():
    """
    Pobiera dane z tabel 'fixtures' oraz 'teams'.
    Zwraca DWIE ramki danych (DataFrames).
    """
    print("📥 Pobieranie danych z bazy SQL...")

    query_fixtures = "SELECT * FROM fixtures"
    query_teams = "SELECT * FROM teams"

    try:
        # 1. Pobranie danych do DataFrame
        df_fixtures = pd.read_sql(query_fixtures, engine)
        df_teams = pd.read_sql(query_teams, engine)

        if df_fixtures.empty or df_teams.empty:
            print("⚠️ Tabela 'fixtures' albo 'teams' jest pusta!")
            return None, None

        # 2. Konwersja daty
        df_fixtures['date'] = pd.to_datetime(df_fixtures['date'])

        # 3. Sortowanie chronologiczne MALEJĄCO (Najnowsze na górze)
        # index 0 = ostatni rozegrany mecz
        df_fixtures = df_fixtures.sort_values(by='date', ascending=False).reset_index(drop=True)

        print(f"✅ Załadowano {len(df_fixtures)} meczów.")
        print(f"✅ Załadowano {len(df_teams)} drużyn.")
        print(f"📅 Zakres dat: od {df_fixtures['date'].min()} do {df_fixtures['date'].max()}")

        # Zwracamy OBIE tabele
        return df_fixtures, df_teams

    except Exception as e:
        print(f"❌ Błąd podczas ładowania danych: {e}")
        return None, None


if __name__ == "__main__":
    # Rozpakowujemy wynik funkcji do dwóch zmiennych
    fixtures_df, teams_df = load_and_sort_data()

