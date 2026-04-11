"""
xgb_model.py — alternatywny model XGBoost dla Dixon-Colesa.
"""
import pandas as pd
from statistics import mean
from config import engine, logger

# ---------------------------------------------------------------------------
# Ligi z pokryciem xG >= 97.4% (Eredivisie i wyżej)
# ---------------------------------------------------------------------------
XGB_LEAGUES = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    88:  "Eredivisie",
    94:  "Primeira Liga",
    71:  "Serie A (Brazil)",
    203: "Süper Lig",
    144: "Jupiler Pro League",
    253: "Major League Soccer",
    40:  "Championship",
}


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load_fixtures() -> pd.DataFrame:
    """Wczytuje fixtures_history dla 12 wybranych lig."""
    league_ids = list(XGB_LEAGUES.keys())
    placeholders = ','.join(str(i) for i in league_ids)

    query = f"""
        SELECT *
        FROM fixtures_history
        WHERE league_id IN ({placeholders})
        ORDER BY date
    """

    df = pd.read_sql(query, engine, parse_dates=['date'])
    logger.info(f"Załadowano {len(df)} meczów z {df['league_id'].nunique()} lig "
                f"({df['season'].min()}–{df['season'].max()}).")
    return df


# ---------------------------------------------------------------------------
# IMPUTE XG — zastąp NULL xG wartością golową
# ---------------------------------------------------------------------------

def impute_xg(df: pd.DataFrame) -> pd.DataFrame:
    """Gdy xg_home lub xg_away jest NULL, podstawia wartość golową jako proxy."""
    null_home = df['xg_home'].isna().sum()
    null_away = df['xg_away'].isna().sum()

    df = df.copy()
    df.loc[df['xg_home'].isna(), 'xg_home'] = df.loc[df['xg_home'].isna(), 'goals_home']
    df.loc[df['xg_away'].isna(), 'xg_away'] = df.loc[df['xg_away'].isna(), 'goals_away']

    logger.info(f"Imputacja xG: uzupełniono {null_home} wartości xg_home, {null_away} xg_away")
    return df


# ---------------------------------------------------------------------------
# TRANSFORM — rozbicie meczu na 2 wiersze (perspektywa każdej drużyny)
# ---------------------------------------------------------------------------

def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Zamienia DataFrame meczowy (1 wiersz = 1 mecz) na DataFrame drużynowy
    (1 wiersz = 1 występ drużyny). Każdy mecz generuje 2 wiersze.
    Wynik posortowany po dacie — gotowy do iteracji ze słownikiem.
    """
    home = pd.DataFrame({
        'fixture_id':    df['fixture_id'],
        'date':          df['date'],
        'season':        df['season'],
        'league_id':     df['league_id'],
        'league_name':   df['league_name'],
        'round_number':  df['round_number'],
        'team_id':       df['home_id'],
        'team_name':     df['home_name'],
        'opponent_id':   df['away_id'],
        'opponent_name': df['away_name'],
        'is_home':       1,
        'goals_scored':    df['goals_home'],
        'goals_conceded':  df['goals_away'],
        'xg_scored':       df['xg_home'],
        'xg_conceded':     df['xg_away'],
    })

    away = pd.DataFrame({
        'fixture_id':    df['fixture_id'],
        'date':          df['date'],
        'season':        df['season'],
        'league_id':     df['league_id'],
        'league_name':   df['league_name'],
        'round_number':  df['round_number'],
        'team_id':       df['away_id'],
        'team_name':     df['away_name'],
        'opponent_id':   df['home_id'],
        'opponent_name': df['home_name'],
        'is_home':       0,
        'goals_scored':    df['goals_away'],
        'goals_conceded':  df['goals_home'],
        'xg_scored':       df['xg_away'],
        'xg_conceded':     df['xg_home'],
    })

    result = pd.concat([home, away]).sort_values('date').reset_index(drop=True)
    logger.info(f"Sezon {result['season'].iloc[0]}: transform → {len(result)} wierszy "
                f"({len(df)} meczów × 2)")
    return result


# ---------------------------------------------------------------------------
# BUILD FEATURES — rolling stats per drużyna (poziom drużyny)
# ---------------------------------------------------------------------------

def build_features(df_transformed: pd.DataFrame) -> pd.DataFrame:
    """
    Iteruje chronologicznie przez występy drużyn i buduje rolling featury
    ze słownika historii. Zwraca tylko wiersze gdzie drużyna rozegrała >= 10 meczów.
    """
    team_history = {}
    rows = []

    for _, row in df_transformed.iterrows():
        team_id     = row['team_id']
        opponent_id = row['opponent_id']
        hist     = team_history.get(team_id, [])
        opp_hist = team_history.get(opponent_id, [])
        games_played     = len(hist)
        opp_games_played = len(opp_hist)

        if games_played >= 10 and opp_games_played >= 10:
            last5      = hist[-5:]
            last10     = hist[-10:]
            opp_last5  = opp_hist[-5:]
            opp_last10 = opp_hist[-10:]

            rows.append({
                # identyfikatory
                'fixture_id':    row['fixture_id'],
                'date':          row['date'],
                'season':        row['season'],
                'league_id':     row['league_id'],
                'team_id':       team_id,
                'team_name':     row['team_name'],
                'opponent_id':   opponent_id,
                'opponent_name': row['opponent_name'],
                'is_home':       row['is_home'],
                'games_played':  games_played,
                # rolling last 5 — drużyna
                'xg_scored_last5':      mean(x['xg_scored']      for x in last5),
                'xg_conceded_last5':    mean(x['xg_conceded']    for x in last5),
                'goals_scored_last5':   mean(x['goals_scored']   for x in last5),
                'goals_conceded_last5': mean(x['goals_conceded'] for x in last5),
                'won_last5':            mean(x['won']            for x in last5),
                'drawn_last5':          mean(x['drawn']          for x in last5),
                'lost_last5':           mean(x['lost']           for x in last5),
                'btts_last5':           mean(x['btts']           for x in last5),
                # rolling last 10 — drużyna
                'xg_scored_last10':      mean(x['xg_scored']      for x in last10),
                'xg_conceded_last10':    mean(x['xg_conceded']    for x in last10),
                'goals_scored_last10':   mean(x['goals_scored']   for x in last10),
                'goals_conceded_last10': mean(x['goals_conceded'] for x in last10),
                'won_last10':            mean(x['won']            for x in last10),
                'drawn_last10':          mean(x['drawn']          for x in last10),
                'lost_last10':           mean(x['lost']           for x in last10),
                'btts_last10':           mean(x['btts']           for x in last10),
                # rolling last 5 — przeciwnik
                'opp_xg_scored_last5':      mean(x['xg_scored']      for x in opp_last5),
                'opp_xg_conceded_last5':    mean(x['xg_conceded']    for x in opp_last5),
                'opp_goals_scored_last5':   mean(x['goals_scored']   for x in opp_last5),
                'opp_goals_conceded_last5': mean(x['goals_conceded'] for x in opp_last5),
                'opp_won_last5':            mean(x['won']            for x in opp_last5),
                'opp_drawn_last5':          mean(x['drawn']          for x in opp_last5),
                'opp_lost_last5':           mean(x['lost']           for x in opp_last5),
                'opp_btts_last5':           mean(x['btts']           for x in opp_last5),
                # rolling last 10 — przeciwnik
                'opp_xg_scored_last10':      mean(x['xg_scored']      for x in opp_last10),
                'opp_xg_conceded_last10':    mean(x['xg_conceded']    for x in opp_last10),
                'opp_goals_scored_last10':   mean(x['goals_scored']   for x in opp_last10),
                'opp_goals_conceded_last10': mean(x['goals_conceded'] for x in opp_last10),
                'opp_won_last10':            mean(x['won']            for x in opp_last10),
                'opp_drawn_last10':          mean(x['drawn']          for x in opp_last10),
                'opp_lost_last10':           mean(x['lost']           for x in opp_last10),
                'opp_btts_last10':           mean(x['btts']           for x in opp_last10),
                # targety
                'goals_scored':   row['goals_scored'],
                'goals_conceded': row['goals_conceded'],
            })

        # aktualizuj słownik zawsze — niezależnie od warunku
        gs = row['goals_scored']
        gc = row['goals_conceded']
        team_history.setdefault(team_id, []).append({
            'xg_scored':      row['xg_scored'],
            'xg_conceded':    row['xg_conceded'],
            'goals_scored':   gs,
            'goals_conceded': gc,
            'won':            int(gs > gc),
            'drawn':          int(gs == gc),
            'lost':           int(gs < gc),
            'btts':           int(gs > 0 and gc > 0),
        })

    result = pd.DataFrame(rows)
    logger.info(f"Sezon {result['season'].iloc[0]}: build_features → {len(result)} wierszy "
                f"(odrzucono {len(df_transformed) - len(result)} wierszy < 10 meczów)")
    return result


# ---------------------------------------------------------------------------
# SPLIT PER SEZON
# ---------------------------------------------------------------------------

def split_by_season(df: pd.DataFrame) -> dict:
    """Dzieli DataFrame na słownik {sezon: DataFrame}, każdy posortowany po dacie.
    Automatycznie wykrywa dostępne sezony — nie wymaga zmian przy nowym sezonie."""
    seasons = sorted(df['season'].unique())
    result = {}
    for season in seasons:
        season_df = df.loc[df['season'] == season].sort_values('date').reset_index(drop=True)
        result[season] = season_df
        logger.info(f"Sezon {season}: {len(season_df)} meczów")
    return result


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    df = load_fixtures()
    df = impute_xg(df)
    seasons = split_by_season(df)

    transformed = {season: transform(df_season) for season, df_season in seasons.items()}

    features = {season: build_features(t_df) for season, t_df in transformed.items()}

    for season, f_df in features.items():
        f_df.to_csv(f'test_features_{season}.csv', index=False)
    logger.info(f"Zapisano pliki test_features dla sezonów: {list(features.keys())}")
