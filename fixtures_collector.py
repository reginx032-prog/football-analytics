import requests
import pandas as pd
import time
import numpy as np
import logging

# --- IMPORTUJEMY STAŁE ---
try:
    from main import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()

# Stałe konfiguracyjne
MATCHES_PER_ROUND = 2  # Liczba meczów na drużynę w rundzie
ROUNDS_TO_FETCH = 5  # Liczba rund do pobrania dla statystyk Last 5
BUFFER_MATCHES = 2  # Dodatkowy bufor meczów


def fetch_xg(fixture_id):
    """Pobiera statystyki Expected Goals (xG) zgodnie z formatem 'expected_goals'."""
    url = f"{BASE_URL}/fixtures/statistics"
    params = {'fixture': fixture_id}
    xg_stats = {"home": None, "away": None}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
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
                        try:
                            xg_stats[side] = float(val)
                        except (ValueError, TypeError):
                            logger.warning(f"Nieprawidłowa wartość xG dla fixture {fixture_id}: {val}")
                    break
        return xg_stats
    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu xG dla fixture {fixture_id}")
        return xg_stats
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd HTTP przy pobieraniu xG dla fixture {fixture_id}: {e}")
        return xg_stats
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd xG dla fixture {fixture_id}: {e}", exc_info=True)
        return xg_stats


def fetch_fixtures(league_id, league_name):
    """Pobiera dynamicznie wyliczoną liczbę meczów dla danej ligi z danymi xG."""
    logger.info(f"Przetwarzanie ligi: {league_name}...")
    url = f"{BASE_URL}/fixtures"
    params = {'league': league_id, 'season': SEASON, 'status': 'FT'}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if not data.get('response'):
            logger.warning(f"Brak danych dla ligi {league_name}")
            return None

        all_matches = data['response']
        all_matches.sort(key=lambda x: x['fixture']['date'], reverse=True)

        unique_teams = set()
        for item in all_matches:
            unique_teams.add(item['teams']['home']['id'])
            unique_teams.add(item['teams']['away']['id'])

        n_teams = len(unique_teams)
        # Wzór: (liczba_drużyn / 2) * liczba_rund + bufor
        required_matches = int((n_teams / MATCHES_PER_ROUND) * ROUNDS_TO_FETCH) + BUFFER_MATCHES
        recent_matches = all_matches[:required_matches]

        fixtures_list = []
        for item in recent_matches:
            f = item.get('fixture', {})
            teams = item.get('teams', {})
            goals = item.get('goals', {})

            f_id = f.get('id')
            h_id = teams.get('home', {}).get('id')
            a_id = teams.get('away', {}).get('id')
            gh = goals.get('home')
            ga = goals.get('away')

            # Walidacja danych
            if any(v is None for v in [f_id, h_id, a_id, gh, ga]):
                logger.warning(f"Niepełne dane dla meczu {f_id}, pomijam")
                continue

            logger.info(f"   Pobieranie xG dla ID {f_id}: {teams['home']['name']} vs {teams['away']['name']}")
            match_xg = fetch_xg(f_id)
            time.sleep(0.05)  # Rate limiting

            # Walidacja xG
            if any(v is None for v in [match_xg['home'], match_xg['away']]):
                logger.warning(f"Brak danych xG dla meczu {f_id}, pomijam")
                continue

            winner_id = h_id if gh > ga else (a_id if ga > gh else 0)

            try:
                round_num = int(''.join(filter(str.isdigit, item['league']['round'])))
            except (KeyError, ValueError, TypeError):
                round_num = 0

            fixtures_list.append({
                'fixture_id': f_id,
                'date': f.get('date'),
                'league_id': league_id,
                'league_name': league_name,
                'round_number': round_num,
                'home_id': h_id,
                'home_name': teams['home']['name'],
                'away_id': a_id,
                'away_name': teams['away']['name'],
                'goals_home': gh,
                'goals_away': ga,
                'xg_home': match_xg['home'],
                'xg_away': match_xg['away'],
                'winner_id': winner_id
            })
        return pd.DataFrame(fixtures_list)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout przy pobieraniu fixtures dla ligi {league_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd HTTP dla ligi {league_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd przy lidze {league_name}: {e}", exc_info=True)
        return None


def calculate_and_save_l5_stats(df_fixtures):
    """Oblicza średnie i mediany statystyk L5. Remis w winner_id to 0."""
    logger.info("Generowanie tabeli statystyk Last 5 (L5) - Średnie + Mediany...")

    # Pobieramy unikalne drużyny
    home_teams = df_fixtures[['home_id', 'home_name']].rename(columns={'home_id': 'id', 'home_name': 'name'})
    away_teams = df_fixtures[['away_id', 'away_name']].rename(columns={'away_id': 'id', 'away_name': 'name'})
    teams = pd.concat([home_teams, away_teams]).drop_duplicates()

    l5_results = []

    for _, team in teams.iterrows():
        t_id = team['id']
        # POPRAWKA: Sortujemy po dacie (najnowsze najpierw) i dopiero potem bierzemy 5 pierwszych
        t_history = df_fixtures[
            (df_fixtures['home_id'] == t_id) | (df_fixtures['away_id'] == t_id)
        ].sort_values('date', ascending=False).head(5)

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

            # Walidacja - pomijamy mecz jeśli brakuje którejkolwiek wartości
            if any(v is None for v in [s, c, xf, xa]):
                logger.warning(f"Brak danych dla meczu {m['fixture_id']} (drużyna {t_id}), pomijam w L5")
                continue

            scored.append(s)
            conceded.append(c)
            xgf.append(xf)
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
            'luck_factor': round(np.mean(scored) - np.mean(xgf), 2),
            'defense_luck_factor': round(np.mean(conceded) - np.mean(xga), 2)
        })

    l5_df = pd.DataFrame(l5_results)
    logger.info(f"Obliczono statystyki L5 dla {len(l5_df)} drużyn")
    try:
        l5_df.to_sql('team_stats_last_5', engine, if_exists='replace', index=False)
        logger.info(f"Zapisano team_stats_last_5 ({len(l5_df)} drużyn).")
    except Exception as e:
        logger.error(f"Błąd zapisu team_stats_last_5: {e}", exc_info=True)


def calculate_league_stats():
    """
    Pobiera dane z tabeli 'fixtures', oblicza średnie ligowe (xG i gole)
    i zapisuje je do nowej tabeli 'league_stats'.
    """
    logger.info("Obliczanie średnich statystyk dla każdej ligi...")

    try:
        # 1. Pobieramy dane z bazy do DataFrame
        df_league = pd.read_sql('fixtures', engine)

        if df_league.empty:
            logger.warning("Tabela 'fixtures' jest pusta. Brak danych do obliczeń.")
            return

        # 2. Grupowanie po league_id i league_name
        # Obliczamy średnie dla goli i xG (zarówno home jak i away)
        league_stats = df_league.groupby(['league_id', 'league_name']).agg({
            'goals_home': 'mean',
            'goals_away': 'mean',
            'xg_home': 'mean',
            'xg_away': 'mean'
        }).reset_index()

        # 3. Zmiana nazw kolumn na czytelne (np. avg_league_xg_home)
        league_stats.columns = [
            'league_id',
            'league_name',
            'l_avg_scored_home',
            'l_avg_scored_away',
            'l_avg_xg_home',
            'l_avg_xg_away'
        ]

        # Zaokrąglamy wyniki
        league_stats = league_stats.round(3)

        # 4. Zapisujemy do bazy danych
        league_stats.to_sql('league_stats', engine, if_exists='replace', index=False)
        logger.info(f"Zaktualizowano tabelę 'league_stats' dla {len(league_stats)} lig.")

        return league_stats

    except Exception as e:
        logger.error(f"Błąd podczas obliczania statystyk ligowych: {e}", exc_info=True)

def run_collection():
    start_time = time.time()
    all_fixtures_df = pd.DataFrame()

    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_fixtures(l_id, l_name)
        if df is not None and not df.empty:
            all_fixtures_df = pd.concat([all_fixtures_df, df], ignore_index=True)
            logger.info(f"Dodano {len(df)} rekordów.")
        time.sleep(1.2)  # Rate limiting

    if not all_fixtures_df.empty:
        all_fixtures_df['date'] = pd.to_datetime(all_fixtures_df['date'])
        # Sortujemy przed zapisem, by najnowsze były na górze
        all_fixtures_df = all_fixtures_df.sort_values(by='date', ascending=False)

        logger.info("Wysyłanie surowych meczów do 'fixtures'...")
        try:
            all_fixtures_df.to_sql('fixtures', engine, if_exists='replace', index=False)
            logger.info(f"Zapisano {len(all_fixtures_df)} meczów do tabeli 'fixtures'")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu fixtures: {e}", exc_info=True)
            return
        calculate_league_stats()
        calculate_and_save_l5_stats(all_fixtures_df)

        duration = round(time.time() - start_time, 2)
        logger.info(f"Gotowe! Całość zajęła {duration}s.")
    else:
        logger.warning("Nie pobrano żadnych meczów.")



if __name__ == "__main__":
    run_collection()