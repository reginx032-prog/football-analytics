import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta
import logging

# --- KONFIGURACJA ---
try:
    from main import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine
except ImportError:
    print("❌ Błąd konfiguracji w main.py - upewnij się, że plik istnieje.")
    exit()

# Stałe konfiguracyjne
SCAN_DAYS = 15  # Liczba dni do skanowania w przód
PREFERRED_BOOKMAKER_ID = 8  # ID preferowanego bukmachera
RATE_LIMIT_DELAY = 0.2  # Opóźnienie między zapytaniami API (sekundy)


def calculate_fair_odds(odds_dict):
    """
    Usuwa marżę bukmacherską (overround) metodą proporcjonalną.
    Zamienia kursy handlowe na rzeczywiste prawdopodobieństwo (Fair Odds).
    """
    # 1. Kursy 1X2 (Zwycięzca meczu)
    h, d, a = odds_dict.get('odd_home', 0), odds_dict.get('odd_draw', 0), odds_dict.get('odd_away', 0)
    if h > 0 and d > 0 and a > 0:
        try:
            margin_sum = (1 / h) + (1 / d) + (1 / a)
            if margin_sum > 0:  # Zabezpieczenie przed dzieleniem przez zero
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


def fetch_upcoming_fixtures_with_odds(league_id, league_name):
    """Skanuje SCAN_DAYS dni, wylicza Fair Odds i bierze tylko pierwszy nadchodzący mecz każdej drużyny."""
    logger.info(f"Rozpoczynam {SCAN_DAYS}-dniowy skan dla: {league_name}...")

    now = datetime.now(timezone.utc)
    all_odds_for_league = {}

    # Zbiór do śledzenia drużyn, które już mają zaplanowany mecz (unikamy duplikowania drużyn)
    teams_already_scheduled = set()

    # 1. PĘTLA PO DNIACH (Zbieranie wszystkich dostępnych kursów)
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

                # Wybieramy preferowanego bukmachera lub pierwszego dostępnego
                selected_bm = next((b for b in bookmakers if b.get('id') == PREFERRED_BOOKMAKER_ID), bookmakers[0])
                bets = selected_bm.get('bets', [])

                m_1x2 = next((b for b in bets if b.get('id') == 1), None)
                v_1x2 = {v['value']: v['odd'] for v in m_1x2.get('values', [])} if m_1x2 else {}

                m_ou = next((b for b in bets if b.get('id') == 5), None)
                v_ou = {v['value']: v['odd'] for v in m_ou.get('values', [])} if m_ou else {}

                m_btts = next((b for b in bets if b.get('id') == 8), None)
                v_btts = {v['value']: v['odd'] for v in m_btts.get('values', [])} if m_btts else {}

                if v_1x2:
                    try:
                        raw_odds = {
                            'odd_home': float(v_1x2.get('Home', 0)),
                            'odd_draw': float(v_1x2.get('Draw', 0)),
                            'odd_away': float(v_1x2.get('Away', 0)),
                            'odd_over_25': float(v_ou.get('Over 2.5', 0)),
                            'odd_under_25': float(v_ou.get('Under 2.5', 0)),
                            'odd_btts_yes': float(v_btts.get('Yes', 0)),
                            'odd_btts_no': float(v_btts.get('No', 0))
                        }

                        fair_odds = calculate_fair_odds(raw_odds)
                        fair_odds['source_bm'] = selected_bm.get('name', 'Unknown')
                        all_odds_for_league[f_id] = fair_odds
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Błąd konwersji kursów dla fixture {f_id}: {e}")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout przy skanowaniu daty {target_date}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP przy skanowaniu daty {target_date}: {e}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd skanowania daty {target_date}: {e}", exc_info=True)

        time.sleep(RATE_LIMIT_DELAY)

    if not all_odds_for_league:
        logger.warning(f"Brak kursów dla ligi {league_name}")
        return None

    # 2. Pobieramy TERMINARZ
    url_fix = f"{BASE_URL}/fixtures"
    params_fix = {'league': league_id, 'season': SEASON}
    try:
        response = requests.get(url_fix, headers=HEADERS, params=params_fix, timeout=10)
        response.raise_for_status()
        res_fix = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd pobierania terminarza dla {league_name}: {e}")
        return None

    # Sortujemy terminarz chronologicznie, żeby filtr unikalności złapał NAJBLIŻSZY mecz
    fix_response = sorted(res_fix.get('response', []), key=lambda x: x.get('fixture', {}).get('date', ''))

    # 3. ŁĄCZENIE Z FILTREM UNIKALNOŚCI DRUŻYN
    final_list = []
    for f_data in fix_response:
        f_id = f_data.get('fixture', {}).get('id')
        if not f_id:
            continue

        if f_id in all_odds_for_league:
            teams = f_data.get('teams', {})
            h_id = teams.get('home', {}).get('id')
            a_id = teams.get('away', {}).get('id')

            if not h_id or not a_id:
                continue

            # Jeśli żadna z drużyn nie ma jeszcze przypisanego meczu w tej tabeli
            if h_id not in teams_already_scheduled and a_id not in teams_already_scheduled:
                try:
                    match_date = pd.to_datetime(f_data['fixture']['date'])
                except (ValueError, TypeError):
                    logger.warning(f"Nieprawidłowa data dla meczu {f_id}")
                    continue

                if match_date > now:
                    # Blokujemy te drużyny dla kolejnych meczów w pętli
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
                        **all_odds_for_league[f_id]
                    })

    if final_list:
        df = pd.DataFrame(final_list)
        logger.info(f"Sukces: Sparowano {len(df)} unikalnych meczów z Fair Odds.")
        return df

    logger.warning(f"Brak przyszłych meczów dla ligi {league_name}")
    return None


def run_odds_collection():
    """Główna pętla zbierająca dane ze wszystkich lig."""
    start_time = time.time()
    all_upcoming_df = pd.DataFrame()

    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_upcoming_fixtures_with_odds(l_id, l_name)
        if df is not None and not df.empty:
            all_upcoming_df = pd.concat([all_upcoming_df, df], ignore_index=True)

        time.sleep(1)  # Rate limiting między ligami

    if not all_upcoming_df.empty:
        all_upcoming_df['date'] = pd.to_datetime(all_upcoming_df['date'])

        # Zapis do bazy (Replace zapewnia czystą tabelę przy każdym skanie)
        try:
            all_upcoming_df.to_sql('upcoming_odds', engine, if_exists='replace', index=False)
            duration = round(time.time() - start_time, 2)
            logger.info(f"Gotowe! Tabela 'upcoming_odds' zaktualizowana w {duration}s.")
            logger.info(f"Łącznie unikalnych meczów: {len(all_upcoming_df)}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu upcoming_odds: {e}", exc_info=True)
    else:
        logger.warning("Nie znaleziono żadnych przyszłych meczów z kursami.")


if __name__ == "__main__":
    run_odds_collection()