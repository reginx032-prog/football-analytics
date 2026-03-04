import time
import requests
import pandas as pd
import numpy as np

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, logger, engine

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
HISTORICAL_SEASONS = [2022, 2023, 2024, 2025]
REQUEST_DELAY      = 0.4   # ~2.5 req/sek, bezpiecznie poniżej limitu

# ---------------------------------------------------------------------------
# EXTRACT — ligi z bazy do DataFrame
# ---------------------------------------------------------------------------

def load_leagues_df():
    """Wczytuje ligi z TOP_20_LEAGUES do DataFrame."""
    df = pd.DataFrame([
        {'league_id': league_id, 'league_name': league_name}
        for league_id, league_name in TOP_20_LEAGUES.items()
    ])
    logger.info(f"Załadowano {len(df)} lig.")
    return df


# ---------------------------------------------------------------------------
# EXTRACT — xG dla pojedynczego meczu
# ---------------------------------------------------------------------------

def fetch_xg(fixture_id):
    """Pobiera xG z /fixtures/statistics. Zwraca None jeśli brak danych."""
    url = f"{BASE_URL}/fixtures/statistics"
    xg = {'home': None, 'away': None}
    try:
        res = requests.get(url, headers=HEADERS, params={'fixture': fixture_id}, timeout=10)
        res.raise_for_status()
        data = res.json().get('response', [])
        if len(data) < 2:
            return xg
        for i, team_data in enumerate(data):
            side = 'home' if i == 0 else 'away'
            for stat in team_data.get('statistics', []):
                if stat.get('type') == 'expected_goals':
                    val = stat.get('value')
                    try:
                        xg[side] = float(val) if val not in (None, '', 'None') else None
                    except (ValueError, TypeError):
                        pass
                    break
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout xG fixture {fixture_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd HTTP xG fixture {fixture_id}: {e}")
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd xG fixture {fixture_id}: {e}", exc_info=True)
    return xg


# ---------------------------------------------------------------------------
# EXTRACT — mecze dla ligi i sezonu
# ---------------------------------------------------------------------------

def fetch_fixtures(league_id, league_name, season):
    """
    Pobiera wszystkie zakończone mecze (FT) dla danej ligi i sezonu.
    W odróżnieniu od fixtures_collector NIE pomija meczów bez xG —
    zapisuje None, żeby nie tracić danych historycznych.
    """
    logger.info(f"  [{season}] {league_name} ...")
    url = f"{BASE_URL}/fixtures"
    params = {'league': league_id, 'season': season, 'status': 'FT'}
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=15)
        res.raise_for_status()
        all_matches = res.json().get('response', [])
        if not all_matches:
            logger.warning(f"  [{season}] {league_name} — brak meczów")
            return pd.DataFrame()

        fixtures_list = []
        for item in all_matches:
            f     = item.get('fixture', {})
            teams = item.get('teams', {})
            goals = item.get('goals', {})

            f_id = f.get('id')
            h_id = teams.get('home', {}).get('id')
            a_id = teams.get('away', {}).get('id')
            gh   = goals.get('home')
            ga   = goals.get('away')

            if any(v is None for v in [f_id, h_id, a_id, gh, ga]):
                logger.warning(f"  Niepełne dane meczu {f_id}, pomijam")
                continue

            xg = fetch_xg(f_id)
            time.sleep(REQUEST_DELAY)

            try:
                round_num = int(''.join(filter(str.isdigit, item['league'].get('round', '0'))))
            except (ValueError, TypeError):
                round_num = 0

            fixtures_list.append({
                'fixture_id':   f_id,
                'date':         f.get('date'),
                'season':       season,
                'league_id':    league_id,
                'league_name':  league_name,
                'round_number': round_num,
                'home_id':      h_id,
                'home_name':    teams['home']['name'],
                'away_id':      a_id,
                'away_name':    teams['away']['name'],
                'goals_home':   gh,
                'goals_away':   ga,
                'xg_home':      xg['home'],   # może być None
                'xg_away':      xg['away'],   # może być None
                'winner_id':    h_id if gh > ga else (a_id if ga > gh else 0)
            })

        logger.info(f"  [{season}] {league_name} — pobrano {len(fixtures_list)} meczów")
        return pd.DataFrame(fixtures_list)

    except requests.exceptions.Timeout:
        logger.error(f"  Timeout fixtures {league_name} {season}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        logger.error(f"  Błąd HTTP fixtures {league_name} {season}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"  Nieoczekiwany błąd {league_name} {season}: {e}", exc_info=True)
        return pd.DataFrame()


if __name__ == '__main__':
    leagues_df = load_leagues_df()

    print(leagues_df.to_string(index=False))
