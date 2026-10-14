import time
import requests
import pandas as pd
import numpy as np

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, logger, engine

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
HISTORICAL_SEASONS    = [2025]
REQUEST_DELAY         = 1   # ~2.5 req/sek, bezpiecznie poniżej limitu
PREFERRED_BOOKMAKER_ID = 8    # Bwin (spójnie z upcoming_odds.py)
DEBUG_LIMIT           = None   # None = pobierz wszystko, int = limit meczów per liga (debug)


class RateLimitError(Exception):
    """Rzucany gdy API zwróci 429 lub błąd limitu w ciele JSON."""
    pass


def _check_rate_limit(body, context=''):
    """Rzuca RateLimitError jeśli API zwróciło komunikat o limicie w body (HTTP 200)."""
    err = body.get('errors', {})
    if isinstance(err, dict):
        msg = err.get('requests', '') or err.get('rateLimit', '')
    elif isinstance(err, list) and err:
        msg = str(err[0])
    else:
        msg = ''
    if msg and 'limit' in msg.lower():
        raise RateLimitError(f"Dzienny limit API wyczerpany ({context}): {msg}")

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

def fetch_xg(fixture_id, retries=3, retry_delay=5):
    """Pobiera xG z /fixtures/statistics. Retry przy 503. Zwraca None jeśli brak danych."""
    url = f"{BASE_URL}/fixtures/statistics"
    xg = {'home': None, 'away': None}
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, headers=HEADERS, params={'fixture': fixture_id}, timeout=10)
            if res.status_code == 429:
                remaining = res.headers.get('x-ratelimit-requests-remaining', '?')
                raise RateLimitError(f"Dzienny limit API wyczerpany (fixture {fixture_id}), pozostało: {remaining}")
            if res.status_code == 503:
                logger.warning(f"503 xG fixture {fixture_id}, próba {attempt}/{retries}, czekam {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            res.raise_for_status()
            body = res.json()
            _check_rate_limit(body, f'xG fixture {fixture_id}')
            data = body.get('response', [])
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
            return xg
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout xG fixture {fixture_id}, próba {attempt}/{retries}")
            time.sleep(retry_delay)
        except RateLimitError:
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP xG fixture {fixture_id}: {e}")
            break
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd xG fixture {fixture_id}: {e}", exc_info=True)
            break
    return xg




# ---------------------------------------------------------------------------
# EXTRACT — mecze dla ligi i sezonu
# ---------------------------------------------------------------------------

def fetch_fixtures(league_id, league_name, season, max_matches=None):
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
        if res.status_code == 429:
            remaining = res.headers.get('x-ratelimit-requests-remaining', '?')
            raise RateLimitError(f"Dzienny limit API wyczerpany przy [{season}] {league_name}, pozostało: {remaining}")
        res.raise_for_status()
        body = res.json()
        _check_rate_limit(body, f'fixtures [{season}] {league_name}')
        all_matches = body.get('response', [])
        if not all_matches:
            logger.warning(f"  [{season}] {league_name} — brak meczów")
            return pd.DataFrame()

        fixtures_list = []
        for item in all_matches:
            if max_matches is not None and len(fixtures_list) >= max_matches:
                break
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

            xg   = fetch_xg(f_id)
            time.sleep(REQUEST_DELAY)

            try:
                round_num = int(''.join(filter(str.isdigit, item['league'].get('round', '0'))))
            except (ValueError, TypeError):
                round_num = 0

            fixtures_list.append({
                'fixture_id':    f_id,
                'date':          f.get('date'),
                'season':        season,
                'league_id':     league_id,
                'league_name':   league_name,
                'round_number':  round_num,
                'home_id':       h_id,
                'home_name':     teams['home']['name'],
                'away_id':       a_id,
                'away_name':     teams['away']['name'],
                'goals_home':    gh,
                'goals_away':    ga,
                'xg_home':       xg['home'],
                'xg_away':       xg['away'],
                'winner_id':     h_id if gh > ga else (a_id if ga > gh else 0),
            })

        logger.info(f"  [{season}] {league_name} — pobrano {len(fixtures_list)} meczów")
        return pd.DataFrame(fixtures_list)

    except RateLimitError:
        raise
    except requests.exceptions.Timeout:
        logger.error(f"  Timeout fixtures {league_name} {season}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        logger.error(f"  Błąd HTTP fixtures {league_name} {season}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"  Nieoczekiwany błąd {league_name} {season}: {e}", exc_info=True)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_fixtures_history(df):
    """Zapisuje pełny DataFrame historyczny do tabeli fixtures_history."""
    try:
        df.to_sql('fixtures_history', engine, if_exists='append', index=False)
        logger.info(f"Zapisano {len(df)} rekordów do tabeli 'fixtures_history'.")
    except Exception as e:
        logger.error(f"Błąd podczas zapisu fixtures_history: {e}", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------

def run_collection():
    start_time = time.time()
    load_leagues_df()
    all_dfs = []

    total_collected = 0
    try:
        for season in HISTORICAL_SEASONS:
            logger.info(f"=== Sezon {season} ===")
            for league_id, league_name in TOP_20_LEAGUES.items():
                remaining = (DEBUG_LIMIT - total_collected) if DEBUG_LIMIT is not None else None
                df = fetch_fixtures(league_id, league_name, season, max_matches=remaining)
                if df is not None and not df.empty:
                    all_dfs.append(df)
                    total_collected += len(df)
                    logger.info(f"  -> Dodano {len(df)} meczów. Łącznie: {total_collected}")
                if DEBUG_LIMIT is not None and total_collected >= DEBUG_LIMIT:
                    logger.info(f"  [DEBUG] Osiągnięto limit {DEBUG_LIMIT} meczów, kończę.")
                    break
                time.sleep(1.2)
            if DEBUG_LIMIT is not None and total_collected >= DEBUG_LIMIT:
                break
    except RateLimitError as e:
        logger.error(f"LIMIT API: {e}")
        logger.warning("Zapisuję zebrane dane i kończę.")

    if not all_dfs:
        logger.warning("Nie pobrano żadnych meczów — brak danych do zapisu.")
        return

    full_df = pd.concat(all_dfs, ignore_index=True)
    full_df['date'] = pd.to_datetime(full_df['date'])
    full_df = full_df.sort_values(by=['season', 'date']).reset_index(drop=True)

    logger.info(f"Łącznie zebrano {len(full_df)} meczów z {full_df['season'].nunique()} sezonów i {full_df['league_id'].nunique()} lig.")

    load_fixtures_history(full_df)

    duration = round(time.time() - start_time, 2)
    logger.info(f"Gotowe! Całość zajęła {duration}s.")


if __name__ == '__main__':
    run_collection()
