import pandas as pd
import logging

# --- IMPORTUJEMY STAŁE ---
try:
    from main import logger, engine
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()


def load_data():
    """
    Ładuje dane z bazy danych PostgreSQL do DataFrame'ów.

    Returns:
        tuple: (team_stats_last_5_df, teams_df)
    """
    logger.info("Ładowanie danych z bazy danych...")

    try:
        # Wczytanie tabeli team_stats_last_5
        team_stats_last_5_df = pd.read_sql_table('team_stats_last_5', engine)
        logger.info(f"Załadowano {len(team_stats_last_5_df)} rekordów z tabeli 'team_stats_last_5'")

        # Wczytanie tabeli teams
        teams_df = pd.read_sql_table('teams', engine)
        logger.info(f"Załadowano {len(teams_df)} rekordów z tabeli 'teams'")

        return team_stats_last_5_df, teams_df

    except Exception as e:
        logger.error(f"Błąd podczas ładowania danych z bazy: {e}", exc_info=True)
        return None, None


def main():
    """Główna funkcja programu."""
    # Ładowanie danych
    team_stats_last_5_df, teams_df = load_data()

    if team_stats_last_5_df is None or teams_df is None:
        logger.error("Nie udało się załadować danych. Kończę program.")
        return

    # Wyświetlenie podstawowych informacji o DataFrame'ach
    logger.info("\n" + "="*50)
    logger.info("TEAM STATS LAST 5 - Informacje:")
    logger.info(f"Kształt: {team_stats_last_5_df.shape}")
    logger.info(f"Kolumny: {list(team_stats_last_5_df.columns)}")
    logger.info("\nPierwsze 3 rekordy:")
    logger.info(f"\n{team_stats_last_5_df.head(3)}")

    logger.info("\n" + "="*50)
    logger.info("TEAMS - Informacje:")
    logger.info(f"Kształt: {teams_df.shape}")
    logger.info(f"Kolumny: {list(teams_df.columns)}")
    logger.info("\nPierwsze 3 rekordy:")
    logger.info(f"\n{teams_df.head(3)}")

    logger.info("\n" + "="*50)
    logger.info("Dane załadowane pomyślnie!")


if __name__ == "__main__":
    main()
