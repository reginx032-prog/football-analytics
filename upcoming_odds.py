import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
import logging

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine

# Stałe konfiguracyjne
SCAN_DAYS = 15  # Liczba dni do skanowania w przód
PREFERRED_BOOKMAKER_ID = 8  # ID preferowanego bukmachera
RATE_LIMIT_DELAY = 0.2  # Opóźnienie między zapytaniami API (sekundy)


# =============================================================================
# TRANSFORM (czysta funkcja, bez I/O)
# =============================================================================

def calculate_fair_odds(odds_dict):
    """
    TRANSFORM: Usuwa marżę bukmacherską (overround) metodą proporcjonalną.
    Zamienia kursy handlowe na rzeczywiste prawdopodobieństwo (Fair Odds).
    Nie modyfikuje oryginalnego słownika.
    """
    odds_dict = dict(odds_dict)  # kopia – bez efektów ubocznych

    # 1. Kursy 1X2 (Zwycięzca meczu)
    h, d, a = odds_dict.get('odd_home', 0), odds_dict.get('odd_draw', 0), odds_dict.get('odd_away', 0)
    if h > 0 and d > 0 and a > 0:
        try:
            margin_sum = (1 / h) + (1 / d) + (1 / a)
            if margin_sum > 0:
                odds_dict['odd_home'] = round(h * margin_sum, 3)
                odds_dict['odd_draw'] = round(d * margin_sum, 3)
                odds_dict['odd_away'] = round(a * margin_sum, 3)
        except ZeroDivisionError:
            logger.warning("Błąd dzielenia przez zero w kursach 1X2")

    # 2. Kursy Over/Under 2.5
    o, u = odds_dict.get('odd_over_25', 0), odds_dict.get('odd_under_25', 0)
    if o > 0 and u > 0:
        try:
            margin_sum = (1 / o) + (1 / u)
            if margin_sum > 0:
                odds_dict['odd_over_25'] = round(o * margin_sum, 3)
                odds_dict['odd_under_25'] = round(u * margin_sum, 3)
        except ZeroDivisionError:
            logger.warning("Błąd dzielenia przez zero w kursach Over/Under")

    # 3. Kursy BTTS (Obie strzelą)
    y, n = odds_dict.get('odd_btts_yes', 0), odds_dict.get('odd_btts_no', 0)
    if y > 0 and n > 0:
        try:
            margin_sum = (1 / y) + (1 / n)
            if margin_sum > 0:
                odds_dict['odd_btts_yes'] = round(y * margin_sum, 3)
                odds_dict['odd_btts_no'] = round(n * margin_sum, 3)
        except ZeroDivisionError:
            logger.warning("Błąd dzielenia przez zero w kursach BTTS")

    return odds_dict


# =============================================================================
# EXTRACT
# =============================================================================

def extract_raw_odds(league_id, league_name):
    """
    EXTRACT: Pobiera surowe kursy bukmacherskie z API dla kolejnych SCAN_DAYS dni.
    Zwraca słownik {fixture_id: raw_odds_dict} z surowymi kursami (przed usunięciem marży).
    """
    logger.info(f"Rozpoczynam {SCAN_DAYS}-dniowy skan kursów dla: {league_name}...")
    now = datetime.now(timezone.utc)
    raw_odds = {}

    for i in range(SCAN_DAYS):
        target_date = (now + timedelta(days=i)).strftime('%Y-%m-%d')
        url_odds = f"{BASE_URL}/odds"
        params_odds = {
            'league': league_id,
            'season': SEASON,
            'date': target_date
        }

        try:
            response = requests.get(url_odds, headers=HEADERS, params=params_odds, timeout=10)
            response.raise_for_status()
            res_odds = response.json()
            odds_response = res_odds.get('response', [])

            for o_item in odds_response:
                f_id = o_item.get('fixture', {}).get('id')
                if not f_id:
                    continue

                bookmakers = o_item.get('bookmakers', [])
                if not bookmakers:
                    continue

                selected_bm = next(
                    (b for b in bookmakers if b.get('id') == PREFERRED_BOOKMAKER_ID),
                    bookmakers[0]
                )
                bets = selected_bm.get('bets', [])

                m_1x2 = next((b for b in bets if b.get('id') == 1), None)
                v_1x2 = {v['value']: v['odd'] for v in m_1x2.get('values', [])} if m_1x2 else {}

                m_ou = next((b for b in bets if b.get('id') == 5), None)
                v_ou = {v['value']: v['odd'] for v in m_ou.get('values', [])} if m_ou else {}

                m_btts = next((b for b in bets if b.get('id') == 8), None)
                v_btts = {v['value']: v['odd'] for v in m_btts.get('values', [])} if m_btts else {}

                if v_1x2:
                    try:
                        raw_odds[f_id] = {
                            'odd_home': float(v_1x2.get('Home', 0)),
                            'odd_draw': float(v_1x2.get('Draw', 0)),
                            'odd_away': float(v_1x2.get('Away', 0)),
                            'odd_over_25': float(v_ou.get('Over 2.5', 0)),
                            'odd_under_25': float(v_ou.get('Under 2.5', 0)),
                            'odd_btts_yes': float(v_btts.get('Yes', 0)),
                            'odd_btts_no': float(v_btts.get('No', 0)),
                            'source_bm': selected_bm.get('name', 'Unknown')
                        }
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Błąd konwersji kursów dla fixture {f_id}: {e}")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout przy skanowaniu daty {target_date}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP przy skanowaniu daty {target_date}: {e}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd skanowania daty {target_date}: {e}", exc_info=True)

        time.sleep(RATE_LIMIT_DELAY)

    if not raw_odds:
        logger.warning(f"Brak kursów dla ligi {league_name}")

    return raw_odds


def extract_fixtures_schedule(league_id, league_name):
    """
    EXTRACT: Pobiera pełny terminarz ligi i sortuje chronologicznie.
    Zwraca posortowaną listę fixture dictów lub None przy błędzie.
    """
    url_fix = f"{BASE_URL}/fixtures"
    params_fix = {'league': league_id, 'season': SEASON}
    try:
        response = requests.get(url_fix, headers=HEADERS, params=params_fix, timeout=10)
        response.raise_for_status()
        res_fix = response.json()
        fix_response = sorted(
            res_fix.get('response', []),
            key=lambda x: x.get('fixture', {}).get('date', '')
        )
        return fix_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd pobierania terminarza dla {league_name}: {e}")
        return None


# =============================================================================
# TRANSFORM
# =============================================================================

def transform_apply_fair_odds(raw_odds):
    """
    TRANSFORM: Usuwa marżę ze słownika surowych kursów.
    Zwraca nowy słownik {fixture_id: fair_odds_dict} bez modyfikacji oryginału.
    """
    return {f_id: calculate_fair_odds(odds) for f_id, odds in raw_odds.items()}


def transform_build_upcoming_df(fix_schedule, fair_odds, league_id, league_name):
    """
    TRANSFORM: Łączy terminarz z kursami, wybiera pierwszy nadchodzący mecz
    każdej drużyny (bez duplikatów). Zwraca DataFrame lub None.
    """
    now = datetime.now(timezone.utc)
    teams_already_scheduled = set()
    final_list = []

    for f_data in fix_schedule:
        f_id = f_data.get('fixture', {}).get('id')
        if not f_id or f_id not in fair_odds:
            continue

        teams = f_data.get('teams', {})
        h_id = teams.get('home', {}).get('id')
        a_id = teams.get('away', {}).get('id')

        if not h_id or not a_id:
            continue

        if h_id not in teams_already_scheduled and a_id not in teams_already_scheduled:
            try:
                match_date = pd.to_datetime(f_data['fixture']['date'])
            except (ValueError, TypeError):
                logger.warning(f"Nieprawidłowa data dla meczu {f_id}")
                continue

            if match_date > now:
                teams_already_scheduled.add(h_id)
                teams_already_scheduled.add(a_id)

                final_list.append({
                    'fixture_id': f_id,
                    'date': f_data['fixture']['date'],
                    'home_id': h_id,
                    'home_name': teams['home'].get('name', 'Unknown'),
                    'away_id': a_id,
                    'away_name': teams['away'].get('name', 'Unknown'),
                    'league_id': league_id,
                    'league_name': league_name,
                    **fair_odds[f_id]
                })

    if final_list:
        df = pd.DataFrame(final_list)
        logger.info(f"Sukces: Sparowano {len(df)} unikalnych meczów z Fair Odds.")
        return df

    logger.warning(f"Brak przyszłych meczów dla ligi {league_name}")
    return None


# =============================================================================
# LOAD
# =============================================================================

def load_upcoming_odds(df):
    """LOAD: Zapisuje upcoming_odds do PostgreSQL (replace zapewnia czystą tabelę)."""
    try:
        df.to_sql('upcoming_odds', engine, if_exists='replace', index=False)
        logger.info(f"Gotowe! Tabela 'upcoming_odds' zaktualizowana.")
        logger.info(f"Łącznie unikalnych meczów: {len(df)}")
    except Exception as e:
        logger.error(f"Błąd podczas zapisu upcoming_odds: {e}", exc_info=True)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def run_odds_collection():
    """Główna pętla zbierająca dane ze wszystkich lig (E → T → L)."""
    start_time = time.time()
    all_dfs = []

    for l_id, l_name in TOP_20_LEAGUES.items():
        # --- EXTRACT ---
        raw_odds = extract_raw_odds(l_id, l_name)
        fix_schedule = extract_fixtures_schedule(l_id, l_name)

        if raw_odds and fix_schedule is not None:
            # --- TRANSFORM ---
            fair_odds = transform_apply_fair_odds(raw_odds)
            df = transform_build_upcoming_df(fix_schedule, fair_odds, l_id, l_name)
            if df is not None:
                all_dfs.append(df)

        time.sleep(1)  # Rate limiting między ligami

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined['date'] = pd.to_datetime(combined['date'])
        combined['is_finished'] = 'no'

        # --- LOAD ---
        load_upcoming_odds(combined)

        duration = round(time.time() - start_time, 2)
        logger.info(f"Całość zajęła {duration}s.")
    else:
        logger.warning("Nie znaleziono żadnych przyszłych meczów z kursami.")


if __name__ == "__main__":
    run_odds_collection()
