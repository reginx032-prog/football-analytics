import requests
import pandas as pd
from sqlalchemy import create_engine
import time
from datetime import datetime, timezone, timedelta

# --- KONFIGURACJA ---
try:
    from main import API_KEY, BASE_URL, DB_URL, HEADERS, TOP_20_LEAGUES, SEASON
except ImportError:
    print("❌ Błąd konfiguracji w main.py - upewnij się, że plik istnieje.")
    exit()

engine = create_engine(DB_URL)


def calculate_fair_odds(odds_dict):
    """
    Usuwa marżę bukmacherską (overround) metodą proporcjonalną.
    Zamienia kursy handlowe na rzeczywiste prawdopodobieństwo (Fair Odds).
    """
    # 1. Kursy 1X2 (Zwycięzca meczu)
    h, d, a = odds_dict.get('odd_home', 0), odds_dict.get('odd_draw', 0), odds_dict.get('odd_away', 0)
    if h > 0 and d > 0 and a > 0:
        margin_sum = (1 / h) + (1 / d) + (1 / a)
        odds_dict['odd_home'] = round(h * margin_sum, 3)
        odds_dict['odd_draw'] = round(d * margin_sum, 3)
        odds_dict['odd_away'] = round(a * margin_sum, 3)

    # 2. Kursy Over/Under 2.5
    o, u = odds_dict.get('odd_over_25', 0), odds_dict.get('odd_under_25', 0)
    if o > 0 and u > 0:
        margin_sum = (1 / o) + (1 / u)
        odds_dict['odd_over_25'] = round(o * margin_sum, 3)
        odds_dict['odd_under_25'] = round(u * margin_sum, 3)

    # 3. Kursy BTTS (Obie strzelą)
    y, n = odds_dict.get('odd_btts_yes', 0), odds_dict.get('odd_btts_no', 0)
    if y > 0 and n > 0:
        margin_sum = (1 / y) + (1 / n)
        odds_dict['odd_btts_yes'] = round(y * margin_sum, 3)
        odds_dict['odd_btts_no'] = round(n * margin_sum, 3)

    return odds_dict


def fetch_upcoming_fixtures_with_odds(league_id, league_name):
    """Skanuje 15 dni, wylicza Fair Odds i bierze tylko pierwszy nadchodzący mecz każdej drużyny."""
    print(f"📡 Rozpoczynam 15-dniowy skan dla: {league_name}...")

    now = datetime.now(timezone.utc)
    all_odds_for_league = {}

    # Zbiór do śledzenia drużyn, które już mają zaplanowany mecz w tym skanie (unikamy duplikowania drużyn)
    teams_already_scheduled = set()

    # 1. PĘTLA PO 15 DNIACH (Zbieranie wszystkich dostępnych kursów)
    for i in range(15):
        target_date = (now + timedelta(days=i)).strftime('%Y-%m-%d')
        url_odds = f"{BASE_URL}/odds"
        params_odds = {
            'league': league_id,
            'season': SEASON,
            'date': target_date
        }

        try:
            res_odds = requests.get(url_odds, headers=HEADERS, params=params_odds).json()
            odds_response = res_odds.get('response', [])

            for o_item in odds_response:
                f_id = o_item['fixture']['id']
                bookmakers = o_item.get('bookmakers', [])
                if not bookmakers: continue

                selected_bm = next((b for b in bookmakers if b['id'] == 8), bookmakers[0])
                bets = selected_bm.get('bets', [])

                m_1x2 = next((b for b in bets if b['id'] == 1), None)
                v_1x2 = {v['value']: v['odd'] for v in m_1x2['values']} if m_1x2 else {}

                m_ou = next((b for b in bets if b['id'] == 5), None)
                v_ou = {v['value']: v['odd'] for v in m_ou['values']} if m_ou else {}

                m_btts = next((b for b in bets if b['id'] == 8), None)
                v_btts = {v['value']: v['odd'] for v in m_btts['values']} if m_btts else {}

                if v_1x2:
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
                    fair_odds['source_bm'] = selected_bm['name']
                    all_odds_for_league[f_id] = fair_odds

        except Exception as e:
            print(f"   ⚠️ Błąd skanowania daty {target_date}: {e}")

        time.sleep(0.2)

    if not all_odds_for_league:
        return None

    # 2. Pobieramy TERMINARZ
    url_fix = f"{BASE_URL}/fixtures"
    params_fix = {'league': league_id, 'season': SEASON}
    res_fix = requests.get(url_fix, headers=HEADERS, params=params_fix).json()

    # Sortujemy terminarz chronologicznie, żeby filtr unikalności złapał NAJBLIŻSZY mecz
    fix_response = sorted(res_fix.get('response', []), key=lambda x: x['fixture']['date'])

    # 3. ŁĄCZENIE Z FILTREM UNIKALNOŚCI DRUŻYN
    final_list = []
    for f_data in fix_response:
        f_id = f_data['fixture']['id']

        if f_id in all_odds_for_league:
            h_id = f_data['teams']['home']['id']
            a_id = f_data['teams']['away']['id']

            # Jeśli żadna z drużyn nie ma jeszcze przypisanego meczu w tej tabeli
            if h_id not in teams_already_scheduled and a_id not in teams_already_scheduled:
                match_date = pd.to_datetime(f_data['fixture']['date'])

                if match_date > now:
                    # Blokujemy te drużyny dla kolejnych meczów w pętli
                    teams_already_scheduled.add(h_id)
                    teams_already_scheduled.add(a_id)

                    t = f_data['teams']
                    final_list.append({
                        'fixture_id': f_id,
                        'date': f_data['fixture']['date'],
                        'home_id': h_id,
                        'home_name': t['home']['name'],
                        'away_id': a_id,
                        'away_name': t['away']['name'],
                        'league_id': league_id,
                        'league_name': league_name,
                        **all_odds_for_league[f_id]
                    })

    if final_list:
        df = pd.DataFrame(final_list)
        print(f"   ✅ Sukces: Sparowano {len(df)} unikalnych meczów z Fair Odds.")
        return df
    return None


def run_odds_collection():
    """Główna pętla zbierająca dane ze wszystkich lig."""
    start_time = time.time()
    all_upcoming_df = pd.DataFrame()

    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_upcoming_fixtures_with_odds(l_id, l_name)
        if df is not None and not df.empty:
            all_upcoming_df = pd.concat([all_upcoming_df, df], ignore_index=True)

        time.sleep(1)

    if not all_upcoming_df.empty:
        all_upcoming_df['date'] = pd.to_datetime(all_upcoming_df['date'])

        # Zapis do bazy (Replace zapewnia czystą tabelę przy każdym skanie)
        all_upcoming_df.to_sql('upcoming_odds', engine, if_exists='replace', index=False)

        duration = round(time.time() - start_time, 2)
        print(f"\n✨ Gotowe! Tabela 'upcoming_odds' zaktualizowana w {duration}s.")
        print(f"📊 Łącznie unikalnych meczów: {len(all_upcoming_df)}")
    else:
        print("📭 Nie znaleziono żadnych przyszłych meczów z kursami.")


if __name__ == "__main__":
    run_odds_collection()