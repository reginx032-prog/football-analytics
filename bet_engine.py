import pandas as pd
import numpy as np
from scipy.stats import poisson
import logging

# --- IMPORTUJEMY STAŁE ---
try:
    from main import logger, engine
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()

def attack_power(stats_df,league_stats_df,upcoming_df):
    stats_df['raw_attack'] = (
            stats_df['avg_xg_for'] * 0.55 +
            stats_df['avg_goals_scored'] * 0.25 +
            stats_df['med_goals_scored'] * 0.20
    ).round(3)

    # 2. Merge dla GOSPODARZA
    df = upcoming_df.merge(
        stats_df[['team_id', 'raw_attack']],
        left_on='home_id',
        right_on='team_id',
        how='left'
    )
    # Zmieniamy nazwę, żeby wiedzieć, że to atak GOSPODARZA
    df = df.rename(columns={'raw_attack': 'home_attack_power'}).drop(columns=['team_id'])

    # 3. Merge dla GOŚCIA (z tej samej tabeli stats_df!)
    df = df.merge(
        stats_df[['team_id', 'raw_attack']],
        left_on='away_id',
        right_on='team_id',
        how='left'
    )
    # Zmieniamy nazwę, żeby wiedzieć, że to atak GOŚCIA
    df = df.rename(columns={'raw_attack': 'away_attack_power'}).drop(columns=['team_id'])
    league_stats_df['avg_perf_away'] = (league_stats_df['l_avg_scored_away'] + league_stats_df['l_avg_xg_away']) / 2
    league_stats_df['avg_perf_home'] = (league_stats_df['l_avg_scored_home'] + league_stats_df['l_avg_xg_home']) / 2
    league_stats_df['avg_perf_home']=league_stats_df['avg_perf_home'].round(2)
    league_stats_df['avg_perf_away'] = league_stats_df['avg_perf_away'].round(2)
    df = df.merge(
        league_stats_df[['league_id', 'avg_perf_away', 'avg_perf_home']],
        on='league_id',
        how='left'
    )

    df['away_attack_power']=df['away_attack_power']/df['avg_perf_away']
    df['home_attack_power'] = df['home_attack_power'] / df['avg_perf_home']
    df['away_attack_power']= df['away_attack_power'].round(2)
    df['home_attack_power'] = df['home_attack_power'].round(2)

    return df


def deffence_power(df_input, stats_df, league_stats_df, upcoming_df):
    # 1. Obliczamy surową obronę (blend)
    stats_df['raw_deffence'] = (
            stats_df['avg_xg_against'] * 0.55 +
            stats_df['avg_goals_conceded'] * 0.25 +
            stats_df['med_goals_conceded'] * 0.20
    ).round(3)

    # 2. Merge dla GOSPODARZA
    df = df_input.merge(
        stats_df[['team_id', 'raw_deffence']],
        left_on='home_id',
        right_on='team_id',
        how='left'
    )
    df = df.rename(columns={'raw_deffence': 'home_deffence_power'}).drop(columns=['team_id'])

    # 3. Merge dla GOŚCIA
    df = df.merge(
        stats_df[['team_id', 'raw_deffence']],
        left_on='away_id',
        right_on='team_id',
        how='left'
    )
    df = df.rename(columns={'raw_deffence': 'away_deffence_power'}).drop(columns=['team_id'])

    # 4. Normalizacja zgodna z wytycznymi:
    # Obrona gospodarza / Średnia goli gości (avg_perf_away)
    df['home_deffence_power'] = (df['home_deffence_power'] / df['avg_perf_away']).round(3)

    # Obrona gościa / Średnia goli gospodarzy (avg_perf_home)
    df['away_deffence_power'] = (df['away_deffence_power'] / df['avg_perf_home']).round(3)

    # Zapis do CSV
    df.to_csv('stats_output.csv', index=False, sep=';', encoding='utf-8')

    return df

def load_data():
    """
    Ładuje 4 tabele z PostgreSQL:
    - team_stats_last_5: statystyki drużyn (L5)
    - teams: mapowanie team_id → league_id
    - league_stats: średnie ligowe (home/away, goals/xG)
    - upcoming_odds: nadchodzące mecze z kursami bukmachera
    """
    logger.info("Ładowanie danych z bazy danych...")

    try:
        team_stats_df = pd.read_sql_table('team_stats_last_5', engine)
        logger.info(f"  team_stats_last_5: {len(team_stats_df)} drużyn")

        teams_df = pd.read_sql_table('teams', engine)
        logger.info(f"  teams:             {len(teams_df)} drużyn")

        league_stats_df = pd.read_sql_table('league_stats', engine)
        logger.info(f"  league_stats:      {len(league_stats_df)} lig")

        upcoming_df = pd.read_sql_table('upcoming_odds', engine)
        logger.info(f"  upcoming_odds:     {len(upcoming_df)} meczów")

        return team_stats_df, teams_df, league_stats_df, upcoming_df

    except Exception as e:
        logger.error(f"Błąd podczas ładowania danych z bazy: {e}", exc_info=True)
        return None, None, None, None


def main():
    """Główna funkcja programu."""
    # Krok 1: Ładowanie danych
    stats_df, teams_df, league_stats_df, upcoming_df = load_data()
    main_df = attack_power(stats_df,league_stats_df,upcoming_df)
    main_df = deffence_power(main_df,stats_df,league_stats_df,upcoming_df)
    if any(x is None for x in [stats_df, teams_df, league_stats_df, upcoming_df]):
        logger.error("Nie udało się załadować danych. Kończę program.")
        return


if __name__ == "__main__":
    main()
