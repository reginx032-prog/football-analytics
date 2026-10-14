import requests
import pandas as pd
import time
import numpy as np
import logging

from config import API_KEY, BASE_URL, HEADERS, TOP_20_LEAGUES, SEASON, logger, engine

# Stałe konfiguracyjne
MATCHES_PER_ROUND = 2  # Liczba meczów na drużynę w rundzie
ROUNDS_TO_FETCH = 5  # Liczba rund do pobrania dla statystyk Last 5
BUFFER_MATCHES = 2  # Dodatkowy bufor meczów


# =============================================================================
# EXTRACT
# =============================================================================

def fetch_xg(fixture_id):
    """EXTRACT: Pobiera statystyki Expected Goals (xG) z API."""
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
    """EXTRACT: Pobiera dynamicznie wyliczoną liczbę meczów dla danej ligi z danymi xG."""
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

            if any(v is None for v in [f_id, h_id, a_id, gh, ga]):
                logger.warning(f"Niepełne dane dla meczu {f_id}, pomijam")
                continue

            logger.info(f"   Pobieranie xG dla ID {f_id}: {teams['home']['name']} vs {teams['away']['name']}")
            match_xg = fetch_xg(f_id)
            time.sleep(0.05)  # Rate limiting

            is_legit = not any(v is None for v in [match_xg['home'], match_xg['away']])
            if not is_legit:
                logger.warning(f"Brak danych xG dla meczu {f_id}, zapisuję z is_legit=False")

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
                'winner_id': winner_id,
                'is_legit': is_legit
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


# =============================================================================
# TRANSFORM
# =============================================================================

def transform_l5_stats(df_fixtures):
    """
    TRANSFORM: Oblicza statystyki Last 5 dla każdej drużyny.
    Zwraca DataFrame bez żadnego zapisu do bazy.
    """
    logger.info("Generowanie tabeli statystyk Last 5 (L5) - Średnie + Mediany...")

    home_teams = df_fixtures[['home_id', 'home_name']].rename(columns={'home_id': 'id', 'home_name': 'name'})
    away_teams = df_fixtures[['away_id', 'away_name']].rename(columns={'away_id': 'id', 'away_name': 'name'})
    teams = pd.concat([home_teams, away_teams]).drop_duplicates()

    l5_results = []

    for _, team in teams.iterrows():
        t_id = team['id']
        t_history = df_fixtures[
            (df_fixtures['home_id'] == t_id) | (df_fixtures['away_id'] == t_id)
        ].sort_values('date', ascending=False).head(5)

        if t_history.empty:
            continue

        scored, conceded, xgf, xga, points = [], [], [], [], 0
        is_legit = True

        for _, m in t_history.iterrows():
            if not m.get('is_legit', True):
                logger.warning(f"Mecz {m['fixture_id']} ma is_legit=False (drużyna {t_id}), flagowanie drużyny")
                is_legit = False

            is_home = int(m['home_id']) == int(t_id)

            s = m['goals_home'] if is_home else m['goals_away']
            c = m['goals_away'] if is_home else m['goals_home']
            xf = m['xg_home'] if is_home else m['xg_away']
            xa = m['xg_away'] if is_home else m['xg_home']

            scored.append(s)
            conceded.append(c)
            if xf is not None:
                xgf.append(xf)
            if xa is not None:
                xga.append(xa)

            w_id = m['winner_id']
            if w_id == 0:
                points += 1
            elif int(w_id) == int(t_id):
                points += 3

        l5_results.append({
            'team_id': t_id,
            'team_name': team['name'],
            'avg_goals_scored': round(np.mean(scored), 2) if scored else None,
            'avg_goals_conceded': round(np.mean(conceded), 2) if conceded else None,
            'avg_xg_for': round(np.mean(xgf), 2) if xgf else None,
            'avg_xg_against': round(np.mean(xga), 2) if xga else None,
            'med_goals_scored': round(np.median(scored), 2) if scored else None,
            'med_goals_conceded': round(np.median(conceded), 2) if conceded else None,
            'med_xg_for': round(np.median(xgf), 2) if xgf else None,
            'med_xg_against': round(np.median(xga), 2) if xga else None,
            'total_points_l5': points,
            'luck_factor': round(np.mean(scored) - np.mean(xgf), 2) if scored and xgf else None,
            'defense_luck_factor': round(np.mean(conceded) - np.mean(xga), 2) if conceded and xga else None,
            'is_legit': is_legit
        })

    l5_df = pd.DataFrame(l5_results)
    logger.info(f"Obliczono statystyki L5 dla {len(l5_df)} drużyn")
    return l5_df


def transform_league_stats(df_fixtures):
    """
    TRANSFORM: Oblicza średnie statystyki ligowe z przekazanego DataFrame.
    Nie czyta z bazy danych. Zwraca DataFrame bez zapisu.
    """
    logger.info("Obliczanie średnich statystyk dla każdej ligi...")

    if df_fixtures.empty:
        logger.warning("Brak danych do obliczeń statystyk ligowych.")
        return pd.DataFrame()

    league_stats = df_fixtures.groupby(['league_id', 'league_name']).agg({
        'goals_home': 'mean',
        'goals_away': 'mean',
        'xg_home': 'mean',
        'xg_away': 'mean'
    }).reset_index()

    league_stats.columns = [
        'league_id',
        'league_name',
        'l_avg_scored_home',
        'l_avg_scored_away',
        'l_avg_xg_home',
        'l_avg_xg_away'
    ]

    return league_stats.round(3)


# =============================================================================
# LOAD
# =============================================================================

def load_all(fixtures_df, l5_df, league_df):
    """
    LOAD: Zapisuje wszystkie tabele w jednym bloku try/catch.
    Jeśli którykolwiek zapis się nie powiedzie, żadna tabela nie zostaje
    zaktualizowana częściowo – błąd jest logowany i propagowany dalej.
    """
    try:
        fixtures_df.to_sql('fixtures', engine, if_exists='replace', index=False)
        logger.info(f"Zapisano {len(fixtures_df)} meczów do tabeli 'fixtures'")

        l5_df.to_sql('team_stats_last_5', engine, if_exists='replace', index=False)
        logger.info(f"Zapisano team_stats_last_5 ({len(l5_df)} drużyn).")

        league_df.to_sql('league_stats', engine, if_exists='replace', index=False)
        logger.info(f"Zaktualizowano tabelę 'league_stats' dla {len(league_df)} lig.")

    except Exception as e:
        logger.error(f"Błąd podczas ładowania danych – pipeline zatrzymany: {e}", exc_info=True)
        raise


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def run_collection():
    start_time = time.time()

    # --- EXTRACT ---
    all_dfs = []
    for l_id, l_name in TOP_20_LEAGUES.items():
        df = fetch_fixtures(l_id, l_name)
        if df is not None and not df.empty:
            all_dfs.append(df)
            logger.info(f"Dodano {len(df)} rekordów.")
        time.sleep(1.2)  # Rate limiting

    if not all_dfs:
        logger.warning("Nie pobrano żadnych meczów.")
        return

    all_fixtures_df = pd.concat(all_dfs, ignore_index=True)
    all_fixtures_df['date'] = pd.to_datetime(all_fixtures_df['date'])
    all_fixtures_df = all_fixtures_df.sort_values(by='date', ascending=False)

    # --- TRANSFORM ---
    l5_df = transform_l5_stats(all_fixtures_df)
    league_df = transform_league_stats(all_fixtures_df)

    # --- LOAD ---
    load_all(all_fixtures_df, l5_df, league_df)

    duration = round(time.time() - start_time, 2)
    logger.info(f"Gotowe! Całość zajęła {duration}s.")


if __name__ == "__main__":
    run_collection()
