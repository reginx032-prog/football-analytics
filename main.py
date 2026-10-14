import requests
import pandas as pd
import time

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine


# =============================================================================
# EXTRACT
# =============================================================================

def extract_teams(league_id, league_name):
    """EXTRACT: Pobiera surową odpowiedź API dla drużyn danej ligi."""
    logger.info(f"Pobieranie danych dla ligi: {league_name} (ID: {league_id})...")
    params = {'league': league_id, 'season': SEASON}

    try:
        response = requests.get(f"{BASE_URL}/teams", headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get('response'):
            logger.warning(f"Brak danych dla ligi {league_name} w sezonie {SEASON}")
            return None

        return data['response']

    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu danych dla ligi {league_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd żądania HTTP dla ligi {league_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd przy lidze {league_name}: {e}", exc_info=True)
        return None


# =============================================================================
# TRANSFORM
# =============================================================================

def transform_teams(raw_response, league_id, league_name):
    """TRANSFORM: Spłaszcza zagnieżdżony JSON API do płaskiego DataFrame."""
    teams_list = []
    for item in raw_response:
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


# =============================================================================
# LOAD
# =============================================================================

def load_teams(df):
    """LOAD: Zapisuje drużyny do PostgreSQL."""
    logger.info("Trwa zapisywanie danych do PostgreSQL...")
    try:
        df.to_sql('teams', engine, if_exists='replace', index=False)
        logger.info("Sukces! Dane zostały zapisane.")
        logger.info(f"Łącznie pobrano {len(df)} drużyn z {len(TOP_20_LEAGUES)} lig.")
    except Exception as e:
        logger.error(f"Błąd podczas zapisu do bazy danych: {e}", exc_info=True)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def main():
    all_dfs = []

    for l_id, l_name in TOP_20_LEAGUES.items():
        # --- EXTRACT ---
        raw = extract_teams(l_id, l_name)
        if raw:
            # --- TRANSFORM ---
            df = transform_teams(raw, l_id, l_name)
            if not df.empty:
                all_dfs.append(df)

        time.sleep(2)  # Rate limiting

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        load_teams(combined_df)  # --- LOAD ---
    else:
        logger.warning("Nie pobrano żadnych danych.")


if __name__ == "__main__":
    main()
