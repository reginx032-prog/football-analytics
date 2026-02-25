import requests
import pandas as pd
import time
import logging

# --- IMPORTUJEMY STAŁE ---
try:
    from main import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()


def fetch_standings(league_id, league_name):
    """
    Pobiera tabelę ligową z API-Football dla danej ligi i sezonu.
    Zwraca DataFrame z kolumnami:
        team_id, team_name, league_id, league_name,
        league_rank, league_points, league_played,
        league_won, league_drawn, league_lost,
        league_gf, league_ga, league_gd
    """
    url = f"{BASE_URL}/standings"
    params = {'league': league_id, 'season': SEASON}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        league_response = data.get('response', [])
        if not league_response:
            logger.warning(f"Brak danych standings dla {league_name}")
            return None

        standings_raw = league_response[0].get('league', {}).get('standings', [])
        if not standings_raw:
            logger.warning(f"Pusta tablica standings dla {league_name}")
            return None

        # standings_raw[0] — pierwsza (i zazwyczaj jedyna) grupa tabeli
        group = standings_raw[0]
        rows = []
        for entry in group:
            team_id = entry.get('team', {}).get('id')
            team_name = entry.get('team', {}).get('name')
            if team_id is None:
                continue
            all_stats = entry.get('all', {})
            goals = all_stats.get('goals', {})
            rows.append({
                'team_id':       team_id,
                'team_name':     team_name,
                'league_id':     league_id,
                'league_name':   league_name,
                'league_rank':   entry.get('rank'),
                'league_points': entry.get('points'),
                'league_played': all_stats.get('played'),
                'league_won':    all_stats.get('win'),
                'league_drawn':  all_stats.get('draw'),
                'league_lost':   all_stats.get('lose'),
                'league_gf':     goals.get('for'),
                'league_ga':     goals.get('against'),
                'league_gd':     entry.get('goalsDiff'),
            })

        if not rows:
            logger.warning(f"Brak wierszy standings dla {league_name}")
            return None

        logger.info(f"Pobrano standings dla {league_name}: {len(rows)} drużyn")
        return pd.DataFrame(rows)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu standings dla {league_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd HTTP przy standings dla {league_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd standings dla {league_name}: {e}", exc_info=True)
        return None


def run_standings_collection():
    """Pobiera tabele ligowe dla wszystkich lig i zapisuje do tabeli 'standings'."""
    logger.info("=== Rozpoczynam aktualizację standings ===")
    start_time = time.time()

    all_standings = pd.DataFrame()

    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_standings(l_id, l_name)
        if df is not None and not df.empty:
            all_standings = pd.concat([all_standings, df], ignore_index=True)
        time.sleep(1.2)  # Rate limiting — API-Football limit

    if all_standings.empty:
        logger.warning("Nie pobrano żadnych standings.")
        return

    try:
        all_standings.to_sql('standings', engine, if_exists='replace', index=False)
        duration = round(time.time() - start_time, 2)
        logger.info(
            f"Zaktualizowano tabelę 'standings': {len(all_standings)} drużyn "
            f"z {all_standings['league_name'].nunique()} lig w {duration}s."
        )
    except Exception as e:
        logger.error(f"Błąd podczas zapisu standings: {e}", exc_info=True)


if __name__ == "__main__":
    run_standings_collection()
