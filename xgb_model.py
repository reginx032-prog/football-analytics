"""
xgb_model.py — alternatywny model XGBoost dla Dixon-Colesa.
"""
import numpy as np
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

# Mecz ligi liczy się do kontekstu lg_* dopiero, gdy zaczął się co najmniej tyle przed
# rozpoczęciem przewidywanego meczu (90 min + przerwa + doliczony czas z zapasem).
LEAGUE_CTX_BUFFER = pd.Timedelta(minutes=150)


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
# FEATURE HELPERS — rekord historii + rolling stats z okna
# ---------------------------------------------------------------------------

def _team_record(scored, conceded, xg_scored, xg_conceded) -> dict:
    """Pojedynczy występ drużyny zapisywany do historii (z perspektywy tej drużyny)."""
    return {
        'xg_scored':      xg_scored,
        'xg_conceded':    xg_conceded,
        'goals_scored':   scored,
        'goals_conceded': conceded,
        'won':            int(scored > conceded),
        'drawn':          int(scored == conceded),
        'lost':           int(scored < conceded),
        'btts':           int(scored > 0 and conceded > 0),
    }


def _rolling(hist: list, prefix: str) -> dict:
    """Rolling featury last5 i last10 z historii drużyny.
    prefix='' dla drużyny, 'opp_' dla rywala. Zakłada len(hist) >= 10."""
    feats = {}
    for window, tag in ((hist[-5:], 'last5'), (hist[-10:], 'last10')):
        feats[f'{prefix}xg_scored_{tag}']      = mean(x['xg_scored']      for x in window)
        feats[f'{prefix}xg_conceded_{tag}']    = mean(x['xg_conceded']    for x in window)
        feats[f'{prefix}goals_scored_{tag}']   = mean(x['goals_scored']   for x in window)
        feats[f'{prefix}goals_conceded_{tag}'] = mean(x['goals_conceded'] for x in window)
        feats[f'{prefix}won_{tag}']            = mean(x['won']            for x in window)
        feats[f'{prefix}drawn_{tag}']          = mean(x['drawn']          for x in window)
        feats[f'{prefix}lost_{tag}']           = mean(x['lost']           for x in window)
        feats[f'{prefix}btts_{tag}']           = mean(x['btts']           for x in window)
    return feats


def _league_context(df: pd.DataFrame) -> dict:
    """
    Średnie ligowe (gole i xG gospodarzy / gości) z meczów tej ligi ZAKOŃCZONYCH przed
    rozpoczęciem meczu — liczą się tylko mecze, które zaczęły się co najmniej
    LEAGUE_CTX_BUFFER wcześniej (mecze trwające w chwili startu są pomijane, także
    gdy wieczorna kolejka MLS / Brazylii przechodzi przez północ UTC).
    Oczekuje danych jednego sezonu. Zwraca {fixture_id: {lg_matches, lg_goals_home, ...}}.
    """
    cols = ['goals_home', 'goals_away', 'xg_home', 'xg_away']
    ctx = {}
    for _, g in df.sort_values(['date', 'fixture_id']).groupby('league_id'):
        sums = np.vstack([np.zeros(len(cols)), g[cols].to_numpy(dtype=float).cumsum(axis=0)])
        n_done = g['date'].searchsorted(g['date'] - LEAGUE_CTX_BUFFER, side='right')
        for fid, n, s in zip(g['fixture_id'], n_done, sums[n_done]):
            ctx[fid] = {'lg_matches': float(n) if n else np.nan,
                        **{f'lg_{c}': (s[i] / n if n else np.nan) for i, c in enumerate(cols)}}
    return ctx


def _league_feats(ctx: dict, is_home: bool) -> dict:
    """Kontekst ligi z perspektywy drużyny: *_for = strona drużyny, *_against = strona rywala."""
    side, opp = ('home', 'away') if is_home else ('away', 'home')
    return {
        'lg_matches':       ctx['lg_matches'],
        'lg_goals_for':     ctx[f'lg_goals_{side}'],
        'lg_goals_against': ctx[f'lg_goals_{opp}'],
        'lg_xg_for':        ctx[f'lg_xg_{side}'],
        'lg_xg_against':    ctx[f'lg_xg_{opp}'],
    }


# ---------------------------------------------------------------------------
# BUILD FEATURES — iteracja PO MECZU (bez wycieku danych)
# ---------------------------------------------------------------------------

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Iteruje chronologicznie po MECZACH (1 wiersz wejścia = 1 mecz) i dla każdego
    buduje 2 wiersze treningowe (perspektywa gospodarza i gościa) z rolling featurów
    ze słownika historii.

    Brak wycieku danych: featury OBU drużyn liczone są wyłącznie z historii SPRZED
    meczu, a historia obu zespołów jest aktualizowana dopiero PO zbudowaniu wierszy —
    dzięki czemu rywal nigdy nie "widzi" przewidywanego meczu we własnym oknie.

    Każdy wiersz dostaje też kontekst ligi (lg_*) — średnie z meczów zakończonych przed jego startem.

    Zwraca tylko mecze, w których OBIE drużyny rozegrały >= 10 spotkań.
    """
    df = df.sort_values(['date', 'fixture_id']).reset_index(drop=True)
    league_ctx = _league_context(df)
    team_history = {}
    rows = []
    kept = 0

    for _, m in df.iterrows():
        home_id, away_id = m['home_id'], m['away_id']
        home_hist = team_history.get(home_id, [])
        away_hist = team_history.get(away_id, [])

        if len(home_hist) >= 10 and len(away_hist) >= 10:
            kept += 1
            ctx = league_ctx[m['fixture_id']]
            base = {
                'fixture_id': m['fixture_id'],
                'date':       m['date'],
                'season':     m['season'],
                'league_id':  m['league_id'],
            }
            # perspektywa gospodarza
            rows.append({
                **base,
                'team_id':       home_id,
                'team_name':     m['home_name'],
                'opponent_id':   away_id,
                'opponent_name': m['away_name'],
                'is_home':       1,
                'games_played':  len(home_hist),
                **_rolling(home_hist, ''),
                **_rolling(away_hist, 'opp_'),
                **_league_feats(ctx, is_home=True),
                'goals_scored':   m['goals_home'],
                'goals_conceded': m['goals_away'],
            })
            # perspektywa gościa
            rows.append({
                **base,
                'team_id':       away_id,
                'team_name':     m['away_name'],
                'opponent_id':   home_id,
                'opponent_name': m['home_name'],
                'is_home':       0,
                'games_played':  len(away_hist),
                **_rolling(away_hist, ''),
                **_rolling(home_hist, 'opp_'),
                **_league_feats(ctx, is_home=False),
                'goals_scored':   m['goals_away'],
                'goals_conceded': m['goals_home'],
            })

        # aktualizacja historii OBU drużyn dopiero PO zbudowaniu wierszy
        team_history.setdefault(home_id, []).append(
            _team_record(m['goals_home'], m['goals_away'], m['xg_home'], m['xg_away']))
        team_history.setdefault(away_id, []).append(
            _team_record(m['goals_away'], m['goals_home'], m['xg_away'], m['xg_home']))

    if not rows:
        logger.warning("build_features: brak meczów spełniających próg >= 10 spotkań.")
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Sezon {result['season'].iloc[0]}: build_features → {len(result)} wierszy "
                f"({kept} meczów × 2, z {len(df)} meczów wejściowych).")
    return result


# ---------------------------------------------------------------------------
# LOAD — zapis featurów do bazy danych
# ---------------------------------------------------------------------------

def load_features(features: dict) -> None:
    """Łączy featury wszystkich sezonów i zapisuje atomicznie do tabeli xgb_features.
    Przy każdym wywołaniu tabela jest nadpisywana (replace)."""
    df_all = pd.concat(features.values(), ignore_index=True)
    df_all.to_sql('xgb_features', engine, if_exists='replace', index=False)
    logger.info(f"Zapisano {len(df_all)} wierszy do tabeli 'xgb_features' "
                f"(sezony: {sorted(features.keys())})")


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

    features = {season: build_features(df_season) for season, df_season in seasons.items()}

    load_features(features)
