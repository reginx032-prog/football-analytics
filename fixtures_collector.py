import requests
import pandas as pd
from sqlalchemy import create_engine
import time
import numpy as np

# --- IMPORTUJEMY STAŁE ---
try:
    from main import API_KEY, BASE_URL, DB_URL, HEADERS, TOP_20_LEAGUES, SEASON
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()

engine = create_engine(DB_URL)


def fetch_xg(fixture_id):
    """Pobiera statystyki Expected Goals (xG) zgodnie z formatem 'expected_goals'."""
    url = f"{BASE_URL}/fixtures/statistics"
    params = {'fixture': fixture_id}
    xg_stats = {"home": 0.0, "away": 0.0}
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        if not data.get('response') or len(data['response']) < 2:
            return xg_stats
        for i, team_data in enumerate(data['response']):
            side = 'home' if i == 0 else 'away'
            stats_list = team_data.get('statistics', [])
            for stat in stats_list:
                if stat.get('type') == 'expected_goals':
                    val = stat.get('value')
                    if val is not None:
                        xg_stats[side] = float(val)
                    break
        return xg_stats
    except Exception as e:
        print(f"      ⚠️ Błąd xG: {e}")
        return xg_stats


def fetch_fixtures(league_id, league_name):
    """Pobiera dynamicznie wyliczoną liczbę meczów dla danej ligi z danymi xG."""
    print(f"📥 Przetwarzanie ligi: {league_name}...")
    url = f"{BASE_URL}/fixtures"
    params = {'league': league_id, 'season': SEASON, 'status': 'FT'}
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        if not data.get('response'):
            return None

        all_matches = data['response']
        all_matches.sort(key=lambda x: x['fixture']['date'], reverse=True)

        unique_teams = set()
        for item in all_matches:
            unique_teams.add(item['teams']['home']['id'])
            unique_teams.add(item['teams']['away']['id'])

        n_teams = len(unique_teams)
        required_matches = int((n_teams / 2) * 5) + 2
        recent_matches = all_matches[:required_matches]

        fixtures_list = []
        for item in recent_matches:
            f = item['fixture'];
            teams = item['teams'];
            goals = item['goals']
            f_id = f['id'];
            h_id = teams['home']['id'];
            a_id = teams['away']['id']
            gh, ga = goals['home'], goals['away']

            print(f"   🔍 xG dla ID {f_id}: {teams['home']['name']} vs {teams['away']['name']}")
            match_xg = fetch_xg(f_id)
            time.sleep(0.05)  # Optymalizacja czasu

            winner_id = h_id if gh > ga else (a_id if ga > gh else 0)
            try:
                round_num = int(''.join(filter(str.isdigit, item['league']['round'])))
            except:
                round_num = 0

            fixtures_list.append({
                'fixture_id': f_id, 'date': f['date'], 'league_id': league_id,
                'league_name': league_name, 'round_number': round_num,
                'home_id': h_id, 'home_name': teams['home']['name'],
                'away_id': a_id, 'away_name': teams['away']['name'],
                'goals_home': gh, 'goals_away': ga,
                'xg_home': match_xg['home'], 'xg_away': match_xg['away'],
                'winner_id': winner_id
            })
        return pd.DataFrame(fixtures_list)
    except Exception as e:
        print(f"❌ Błąd przy lidze {league_name}: {e}")
        return None


def calculate_and_save_l5_stats(df_fixtures):
    """Oblicza średnie i mediany statystyk L5. Remis w winner_id to 0."""
    print("\n🧠 Generowanie tabeli statystyk Last 5 (L5) - Średnie + Mediany...")

    # Pobieramy unikalne drużyny
    home_teams = df_fixtures[['home_id', 'home_name']].rename(columns={'home_id': 'id', 'home_name': 'name'})
    away_teams = df_fixtures[['away_id', 'away_name']].rename(columns={'away_id': 'id', 'away_name': 'name'})
    teams = pd.concat([home_teams, away_teams]).drop_duplicates()

    l5_results = []

    for _, team in teams.iterrows():
        t_id = team['id']
        # Pobieramy 5 najnowszych meczów drużyny
        t_history = df_fixtures[(df_fixtures['home_id'] == t_id) | (df_fixtures['away_id'] == t_id)].head(5)

        if t_history.empty:
            continue

        scored, conceded, xgf, xga, points = [], [], [], [], 0

        for _, m in t_history.iterrows():
            is_home = int(m['home_id']) == int(t_id)

            # Gole i xG
            s = m['goals_home'] if is_home else m['goals_away']
            c = m['goals_away'] if is_home else m['goals_home']
            xf = m['xg_home'] if is_home else m['xg_away']
            xa = m['xg_away'] if is_home else m['xg_home']

            scored.append(s);
            conceded.append(c);
            xgf.append(xf);
            xga.append(xa)

            # --- POPRAWIONA LOGIKA PUNKTACJI ---
            w_id = m['winner_id']

            # Sprawdzamy czy winner_id to 0 (Twoje oznaczenie remisu)
            if w_id == 0:
                points += 1
            # Sprawdzamy czy to ID naszej drużyny (wygrana)
            elif int(w_id) == int(t_id):
                points += 3
            # W przeciwnym razie porażka (0 pkt)

        # Dodajemy do wyników średnie i mediany
        l5_results.append({
            'team_id': t_id,
            'team_name': team['name'],
            'avg_goals_scored': round(np.mean(scored), 2),
            'avg_goals_conceded': round(np.mean(conceded), 2),
            'avg_xg_for': round(np.mean(xgf), 2),
            'avg_xg_against': round(np.mean(xga), 2),
            # DODANE MEDIANY
            'med_goals_scored': round(np.median(scored), 2),
            'med_goals_conceded': round(np.median(conceded), 2),
            'med_xg_for': round(np.median(xgf), 2),
            'med_xg_against': round(np.median(xga), 2),
            'total_points_l5': points,
            'luck_factor': round(np.mean(scored) - np.mean(xgf), 2)
        })

    l5_df = pd.DataFrame(l5_results)
    l5_df.to_sql('team_stats_last_5', engine, if_exists='replace', index=False)
    print(f"✅ Zaktualizowano tabelę 'team_stats_last_5'.")


def run_collection():
    start_time = time.time()
    all_fixtures_df = pd.DataFrame()

    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_fixtures(l_id, l_name)
        if df is not None and not df.empty:
            all_fixtures_df = pd.concat([all_fixtures_df, df], ignore_index=True)
            print(f"✅ Dodano {len(df)} rekordów.")
        time.sleep(1.2)

    if not all_fixtures_df.empty:
        all_fixtures_df['date'] = pd.to_datetime(all_fixtures_df['date'])
        # Sortujemy przed zapisem, by najnowsze były na górze
        all_fixtures_df = all_fixtures_df.sort_values(by='date', ascending=False)

        print("\n💾 Wysyłanie surowych meczów do 'fixtures'...")
        all_fixtures_df.to_sql('fixtures', engine, if_exists='replace', index=False)

        # NOWOŚĆ: Generowanie i zapisywanie tabeli Last 5
        calculate_and_save_l5_stats(all_fixtures_df)

        duration = round(time.time() - start_time, 2)
        print(f"✨ Gotowe! Całość zajęła {duration}s.")


if __name__ == "__main__":
    run_collection()