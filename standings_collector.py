import requests
import pandas as pd
import time

from config import BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine


# =============================================================================
# EXTRACT
# =============================================================================

def extract_standings(league_id, league_name):
    """EXTRACT: Pobiera surową odpowiedź API standings dla danej ligi."""
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
        return standings_raw[0]

    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu standings dla {league_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd HTTP przy standings dla {league_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd standings dla {league_name}: {e}", exc_info=True)
        return None


# =============================================================================
# TRANSFORM
# =============================================================================

def transform_standings(raw_group, league_id, league_name):
    """TRANSFORM: Spłaszcza surową grupę standings do płaskiego DataFrame."""
    rows = []
    for entry in raw_group:
        team_id = entry.get('team', {}).get('id')
        if team_id is None:
            continue
        all_stats = entry.get('all', {})
        goals = all_stats.get('goals', {})
        rows.append({
            'team_id':       team_id,
            'team_name':     entry.get('team', {}).get('name'),
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
        return pd.DataFrame()

    logger.info(f"Przekształcono standings dla {league_name}: {len(rows)} drużyn")
    return pd.DataFrame(rows)


# =============================================================================
# LOAD
# =============================================================================

def load_standings(df):
    """LOAD: Zapisuje tabelę standings do PostgreSQL."""
    try:
        df.to_sql('standings', engine, if_exists='replace', index=False)
        logger.info(
            f"Zaktualizowano tabelę 'standings': {len(df)} drużyn "
            f"z {df['league_name'].nunique()} lig."
        )
    except Exception as e:
        logger.error(f"Błąd podczas zapisu standings: {e}", exc_info=True)
        raise


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def run_standings_collection():
    """Pobiera tabele ligowe dla wszystkich lig i zapisuje do tabeli 'standings' (E → T → L)."""
    logger.info("=== Rozpoczynam aktualizację standings ===")
    start_time = time.time()

    all_dfs = []

    for l_id, l_name in TOP_20_LEAGUES.items():
        # --- EXTRACT ---
        raw_group = extract_standings(l_id, l_name)
        if raw_group is not None:
            # --- TRANSFORM ---
            df = transform_standings(raw_group, l_id, l_name)
            if not df.empty:
                all_dfs.append(df)

        time.sleep(1.2)  # Rate limiting — API-Football limit

    if not all_dfs:
        logger.warning("Nie pobrano żadnych standings.")
        return

    combined = pd.concat(all_dfs, ignore_index=True)

    # --- LOAD ---
    load_standings(combined)

    duration = round(time.time() - start_time, 2)
    logger.info(f"Gotowe! Całość zajęła {duration}s.")


if __name__ == "__main__":
    run_standings_collection()
