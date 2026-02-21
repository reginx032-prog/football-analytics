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


    return df
def merge_corrections(df_input, stats_df):
    cols = ['team_id', 'luck_factor', 'defense_luck_factor', 'total_points_l5']

    # Gospodarz
    df = df_input.merge(
        stats_df[cols],
        left_on='home_id',
        right_on='team_id',
        how='left'
    )
    df = df.rename(columns={
        'luck_factor': 'home_luck',
        'defense_luck_factor': 'home_def_luck',
        'total_points_l5': 'home_form_pts'
    }).drop(columns=['team_id'])

    # Gość
    df = df.merge(
        stats_df[cols],
        left_on='away_id',
        right_on='team_id',
        how='left'
    )
    df = df.rename(columns={
        'luck_factor': 'away_luck',
        'defense_luck_factor': 'away_def_luck',
        'total_points_l5': 'away_form_pts'
    }).drop(columns=['team_id'])
    # Zapis do CSV
    return df
def lambda_count(main_df):
    main_df['lambda_home']= (main_df['home_attack_power']*main_df['away_deffence_power']).round(3)
    main_df['lambda_away']=(main_df['away_attack_power']*main_df['home_deffence_power']).round(3)
    return main_df
def lambda_corrections(main_df):
    main_df['correct_lambda_home'] = (main_df['lambda_home'] + (main_df['away_def_luck'] * 0.10))
    main_df['correct_lambda_home'] += (main_df['home_luck'] * -1 * 0.18)
    main_df['correct_lambda_home'] *= (0.88 + (main_df['home_form_pts'] / 15 * 0.24))

    main_df['correct_lambda_away'] = (main_df['lambda_away'] + (main_df['home_def_luck'] * 0.10))
    main_df['correct_lambda_away'] += (main_df['away_luck'] * -1 * 0.18)
    main_df['correct_lambda_away'] *= (0.88 + (main_df['away_form_pts'] / 15 * 0.24))

    main_df['correct_lambda_away']=main_df['correct_lambda_away'].round(3)
    main_df['correct_lambda_home']=main_df['correct_lambda_home'].round(3)

    return main_df
RHO = -0.04  # Dixon-Coles: korekta zależności dla niskich wyników


def _dc_tau(i, j, lh, la):
    """Korekta Dixon-Coles dla 4 niskich wyników."""
    if i == 0 and j == 0:
        return 1 - lh * la * RHO   # 0:0 → w górę
    elif i == 1 and j == 0:
        return 1 + la * RHO        # 1:0 → w dół
    elif i == 0 and j == 1:
        return 1 + lh * RHO        # 0:1 → w dół
    elif i == 1 and j == 1:
        return 1 - RHO             # 1:1 → w górę
    return 1.0


def _build_matrix(lh, la):
    """Macierz 10×10 P(i goli gosp, j goli gość) z korektą Dixon-Coles."""
    lh = max(lh, 0.01)
    la = max(la, 0.01)
    m = np.zeros((10, 10))
    for i in range(10):
        for j in range(10):
            m[i, j] = poisson.pmf(i, lh) * poisson.pmf(j, la) * _dc_tau(i, j, lh, la)
    m /= m.sum()  # renormalizacja → suma = 1.0
    return m


def compute_markets(main_df):
    """
    Dla każdego meczu buduje macierz wyników i sumuje komórki:
    - 1X2, Over/Under 2.5, BTTS, Podwójna szansa
    - Kursy fair = 1 / prawdopodobieństwo
    """
    rows = []
    for _, row in main_df.iterrows():
        m = _build_matrix(row['correct_lambda_home'], row['correct_lambda_away'])

        # 1X2
        p_home = sum(m[i, j] for i in range(10) for j in range(10) if i > j)
        p_draw = sum(m[i, i] for i in range(10))
        p_away = sum(m[i, j] for i in range(10) for j in range(10) if j > i)

        # Over / Under 2.5
        p_over25  = sum(m[i, j] for i in range(10) for j in range(10) if i + j >= 3)
        p_under25 = 1.0 - p_over25

        # BTTS
        p_btts_yes = sum(m[i, j] for i in range(10) for j in range(10) if i >= 1 and j >= 1)
        p_btts_no  = 1.0 - p_btts_yes

        # Podwójna szansa
        p_1x = p_home + p_draw
        p_x2 = p_away + p_draw
        p_12 = p_home + p_away

        def fair(p):
            return round(1 / p, 3) if p > 0 else 0.0

        rows.append({
            'p_home':         round(p_home, 4),
            'p_draw':         round(p_draw, 4),
            'p_away':         round(p_away, 4),
            'p_over25':       round(p_over25, 4),
            'p_under25':      round(p_under25, 4),
            'p_btts_yes':     round(p_btts_yes, 4),
            'p_btts_no':      round(p_btts_no, 4),
            'p_1x':           round(p_1x, 4),
            'p_x2':           round(p_x2, 4),
            'p_12':           round(p_12, 4),
            'fair_home':      fair(p_home),
            'fair_draw':      fair(p_draw),
            'fair_away':      fair(p_away),
            'fair_over25':    fair(p_over25),
            'fair_under25':   fair(p_under25),
            'fair_btts_yes':  fair(p_btts_yes),
            'fair_btts_no':   fair(p_btts_no),
        })

    results_df = pd.DataFrame(rows, index=main_df.index)
    return pd.concat([main_df, results_df], axis=1)


def generate_hints(main_df):
    """Flaguje anomalie statystyczne mogące wpłynąć na trafność predykcji."""
    hints_list = []
    for _, row in main_df.iterrows():
        hints = []
        home = row['home_name']
        away = row['away_name']

        # Regresja szczęścia w ataku
        for name, luck in [(home, row.get('home_luck', 0)), (away, row.get('away_luck', 0))]:
            if abs(luck) > 0.4:
                tag = "szczęście" if luck > 0 else "pech"
                hints.append(f"[LUCK] {name}: {tag} w ataku ({luck:+.2f}) → regresja")

        # Szczęście obrony
        for name, dluck in [(home, row.get('home_def_luck', 0)), (away, row.get('away_def_luck', 0))]:
            if abs(dluck) > 0.5:
                tag = "niezasłużona szczelność" if dluck > 0 else "pech obronny"
                hints.append(f"[DEF_LUCK] {name}: {tag} ({dluck:+.2f})")

        # Forma
        for name, pts in [(home, row.get('home_form_pts', 7)), (away, row.get('away_form_pts', 7))]:
            if pts >= 11:
                hints.append(f"[FORMA] {name}: świetna ({pts}/15 pkt)")
            elif pts <= 3:
                hints.append(f"[FORMA] {name}: fatalna ({pts}/15 pkt)")

        # Siła ataku vs. średnia ligi
        for name, att in [(home, row.get('home_attack_power', 1.0)), (away, row.get('away_attack_power', 1.0))]:
            if att > 1.35:
                hints.append(f"[ATAK] {name}: elitarny ({att:.2f}×)")
            elif att < 0.65:
                hints.append(f"[ATAK] {name}: słaby ({att:.2f}×)")

        # Kontekst BTTS
        p_btts = row.get('p_btts_yes', 0.5)
        if p_btts > 0.60:
            hints.append(f"[BTTS] Obie strzelą bardzo prawdopodobne ({p_btts:.0%})")
        elif p_btts < 0.35:
            hints.append(f"[BTTS] Obie strzelą mało prawdopodobne ({p_btts:.0%})")

        hints_list.append(' | '.join(hints) if hints else '')

    main_df = main_df.copy()
    main_df['hints'] = hints_list
    return main_df
def build_output_df(main_df):
    """Wyciąga do osobnego df tylko kolumny potrzebne do analizy value betów."""
    cols = [
        # Identyfikatory
        'league_id', 'league_name', 'fixture_id', 'date', 'home_name', 'away_name','home_id', 'away_id',
        # Prawdopodobieństwa modelu
        # Kursy fair (model)
        'fair_home', 'fair_draw', 'fair_away',
        'fair_over25', 'fair_under25',
        'fair_btts_yes', 'fair_btts_no',
        # Kursy bukmachera (Fair Odds po usunięciu marży)
        'odd_home', 'odd_draw', 'odd_away',
        'odd_over_25', 'odd_under_25',
        'odd_btts_yes', 'odd_btts_no',
        # Wskazówki
        'hints',
    ]
    # Bierzemy tylko kolumny które faktycznie istnieją w df
    existing = [c for c in cols if c in main_df.columns]
    return main_df[existing].copy()


def find_value_bets(output_df, min_edge=0.05):
    """
    Szuka value betów: sytuacji gdzie kurs bukmachera > kurs fair modelu.

    Edge = (odd_bookie / fair_odd) - 1
    Np. edge=0.10 → bukmacher przepłaca o 10% względem modelu → value bet.

    Parametr min_edge: minimalny próg edge żeby zakład był uznany za value (domyślnie 5%).
    Zwraca posortowany df z value betami.
    """
    # Pary: (kolumna kursu bukmachera, kolumna kursu fair modelu, etykieta rynku)
    markets = [
        ('odd_home',    'fair_home',     '1'),
        ('odd_draw',    'fair_draw',     'X'),
        ('odd_away',    'fair_away',     '2'),
        ('odd_over_25', 'fair_over25',   'Over 2.5'),
        ('odd_under_25','fair_under25',  'Under 2.5'),
        ('odd_btts_yes','fair_btts_yes', 'BTTS Yes'),
        ('odd_btts_no', 'fair_btts_no',  'BTTS No'),
    ]

    value_rows = []
    for _, row in output_df.iterrows():
        for bookie_col, fair_col, label in markets:
            bookie_odd = row.get(bookie_col, 0)
            fair_odd   = row.get(fair_col, 0)

            if bookie_odd <= 1.0 or fair_odd <= 1.0:
                continue

            edge = round((bookie_odd / fair_odd) - 1, 4)

            if edge >= min_edge:
                value_rows.append({
                    'date':        row['date'],
                    'league_name': row['league_name'],
                    'fixture_id':  row['fixture_id'],
                    'home_name':   row['home_name'],
                    'away_name':   row['away_name'],
                    'market':      label,
                    'fair_odd':    fair_odd,
                    'bookie_odd':  bookie_odd,
                    'edge':        edge,
                    'hints':       row.get('hints', ''),
                })

    if not value_rows:
        logger.info("Brak value betów przy progu edge >= {min_edge:.0%}")
        return pd.DataFrame()

    vb_df = pd.DataFrame(value_rows).sort_values('edge', ascending=False)
    logger.info(f"Znaleziono {len(vb_df)} value betów (próg edge >= {min_edge:.0%})")
    return vb_df


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
    if any(x is None for x in [stats_df, teams_df, league_stats_df, upcoming_df]):
        logger.error("Nie udało się załadować danych. Kończę program.")
        return
    main_df = attack_power(stats_df,league_stats_df,upcoming_df)
    main_df = deffence_power(main_df,stats_df,league_stats_df,upcoming_df)
    main_df = merge_corrections(main_df, stats_df)
    main_df = lambda_count(main_df)
    main_df = lambda_corrections(main_df)
    main_df = compute_markets(main_df)
    main_df = generate_hints(main_df)
    main_df.to_csv('stats_output.csv', index=False, sep=';', encoding='utf-8')
    logger.info(f"Zapisano wyniki do stats_output.csv ({len(main_df)} meczów)")

    output_df = build_output_df(main_df)
    output_df.to_csv('output.csv', index=False, sep=';', encoding='utf-8')
    logger.info(f"Zapisano skrót do output.csv ({len(output_df)} meczów)")

    vb_df = find_value_bets(output_df, min_edge=1)
    if not vb_df.empty:
        vb_df.to_csv('value_bets.csv', index=False, sep=';', encoding='utf-8')
        logger.info(f"Zapisano value_bets.csv ({len(vb_df)} zakładów)")

if __name__ == "__main__":
    main()
