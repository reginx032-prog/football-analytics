import time
import requests
import pandas as pd
import numpy as np

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, logger, engine

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
HISTORICAL_SEASONS    = [2026]
REQUEST_DELAY         = 1   # ~2.5 req/sek, bezpiecznie poniżej limitu
PREFERRED_BOOKMAKER_ID = 8    # Bwin (spójnie z upcoming_odds.py)
DEBUG_LIMIT           = None   # None = pobierz wszystko, int = limit meczów per liga (debug)


class RateLimitError(Exception):
    """Rzucany gdy API zwróci 429 lub błąd limitu w ciele JSON."""
    pass


# Konfiguracja ponawiania przy limitach / błędach serwera
MAX_API_RETRIES = 5
PER_MINUTE_WAIT = 61   # okno limitu "na minutę" w API-Football (300 req/min na planie Pro)
SERVER_ERR_WAIT = 5    # 503 / timeout


def _daily_remaining(res):
    """Dzienny zapas zapytań z nagłówka x-ratelimit-requests-remaining (None gdy nieznany)."""
    try:
        return int(res.headers.get('x-ratelimit-requests-remaining'))
    except (TypeError, ValueError):
        return None


def _is_daily_exhausted(res):
    rem = _daily_remaining(res)
    return rem is not None and rem <= 0


def _retry_after(res):
    """Ile sekund czekać po 429 — z nagłówka Retry-After albo domyślnie okno minutowe."""
    try:
        return int(res.headers.get('Retry-After'))
    except (TypeError, ValueError):
        return PER_MINUTE_WAIT


def _api_get(url, params, context=''):
    """
    GET do API-Football z rozróżnieniem DWÓCH różnych limitów:
      • limit DZIENNY (x-ratelimit-requests-remaining == 0 lub errors.requests)
        → RateLimitError (fatal, trzeba czekać do jutra),
      • limit NA MINUTĘ (HTTP 429 lub errors.rateLimit przy HTTP 200, gdy dzienny zapas > 0)
        → odczekanie i ponowienie (przejściowe),
      • 503 / timeout → ponowienie.
    Zwraca sparsowane body (dict) albo None, gdy mimo prób nie udało się pobrać.
    """
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            res = requests.get(url, headers=HEADERS, params=params, timeout=15)
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout {context}, próba {attempt}/{MAX_API_RETRIES}, czekam {SERVER_ERR_WAIT}s...")
            time.sleep(SERVER_ERR_WAIT)
            continue
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP {context}: {e}")
            return None

        # HTTP 429 — limit na minutę, chyba że wyczerpany jest też zapas dzienny
        if res.status_code == 429:
            if _is_daily_exhausted(res):
                raise RateLimitError(f"Dzienny limit API wyczerpany ({context}).")
            wait = _retry_after(res)
            logger.warning(f"Limit na minutę (429) {context}; dzienny zapas: {_daily_remaining(res)}. "
                           f"Czekam {wait}s i ponawiam ({attempt}/{MAX_API_RETRIES})...")
            time.sleep(wait)
            continue

        if res.status_code == 503:
            logger.warning(f"503 {context}, próba {attempt}/{MAX_API_RETRIES}, czekam {SERVER_ERR_WAIT}s...")
            time.sleep(SERVER_ERR_WAIT)
            continue

        try:
            res.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP {context}: {e}")
            return None

        body = res.json()
        err = body.get('errors')
        if isinstance(err, dict) and err:
            daily_msg = err.get('requests', '')
            if daily_msg and 'limit' in daily_msg.lower():
                raise RateLimitError(f"Dzienny limit API wyczerpany ({context}): {daily_msg}")
            minute_msg = err.get('rateLimit', '')
            if minute_msg:
                if _is_daily_exhausted(res):
                    raise RateLimitError(f"Dzienny limit API wyczerpany ({context}): {minute_msg}")
                logger.warning(f"Limit na minutę {context}: {minute_msg}. "
                               f"Czekam {PER_MINUTE_WAIT}s i ponawiam ({attempt}/{MAX_API_RETRIES})...")
                time.sleep(PER_MINUTE_WAIT)
                continue
            logger.warning(f"API zwróciło errors {context}: {err}")  # inny błąd API, nie limit
        return body

    logger.error(f"{context}: wyczerpano {MAX_API_RETRIES} prób.")
    return None

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
    """Pobiera xG z /fixtures/statistics. Zwraca {'home','away'} (None gdy brak danych)."""
    xg = {'home': None, 'away': None}
    body = _api_get(f"{BASE_URL}/fixtures/statistics", {'fixture': fixture_id}, f'xG fixture {fixture_id}')
    if not body:
        return xg
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
    body = _api_get(f"{BASE_URL}/fixtures",
                    {'league': league_id, 'season': season, 'status': 'FT'},
                    f'fixtures [{season}] {league_name}')
    if not body:
        return pd.DataFrame()

    all_matches = body.get('response', [])
    if not all_matches:
        logger.warning(f"  [{season}] {league_name} — brak meczów")
        return pd.DataFrame()

    fixtures_list = []
    try:
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

            xg = fetch_xg(f_id)
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
    except RateLimitError:
        raise  # dzienny limit — przerwij, run_collection zapisze zebrane dane
    except Exception as e:
        logger.error(f"  Nieoczekiwany błąd {league_name} {season}: {e}", exc_info=True)

    logger.info(f"  [{season}] {league_name} — pobrano {len(fixtures_list)} meczów")
    return pd.DataFrame(fixtures_list)


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
