"""Testy pipeline'u XGBoost: brak wycieku danych w cechach, macierz wyników, metryki, podział czasowy."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import brentq
from scipy.stats import chisquare, poisson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xgb_model import LEAGUE_CTX_BUFFER, _league_context, build_features, impute_xg  # noqa: E402
from xgb_train import (  # noqa: E402
    LOSSES, MARKETS, NON_FEATURES, TEST_START, VALID_START, add_derived_features, blend_lambdas,
    calibration_1x2_joint, calibration_in_the_large, feature_columns, fit_blend_weight, fit_rho,
    league_avg_lambdas, market_outcomes, market_probs, match_losses, oof_lambdas,
    paired_comparison, rps_1x2, score_matrix, split_by_time, to_matches,
)

FEATURE_STATS = ['xg_scored', 'xg_conceded', 'goals_scored', 'goals_conceded',
                 'won', 'drawn', 'lost', 'btts']
H = lambda hours, minutes=0: pd.Timedelta(hours=hours, minutes=minutes)

# Liga A: 6 drużyn, kolejka jednego dnia; dwa mecze o tej samej godzinie i jeden dokładnie
# LEAGUE_CTX_BUFFER wcześniej. Liga B (jak MLS): 8 drużyn, kolejka przechodzi przez północ UTC.
LEAGUE_A = dict(league_id=39, teams=range(1, 7), cycles=4, first_day='2024-08-01',
                slots=[H(12, 30), H(15), H(15)])
LEAGUE_B = dict(league_id=253, teams=range(101, 109), cycles=3, first_day='2024-08-02',
                slots=[H(21), H(23), H(24, 30), H(26, 30)])


def _round_robin(teams: list) -> list:
    """Terminarz metodą kołową: lista kolejek, w każdej każda drużyna gra dokładnie raz."""
    teams, rounds = list(teams), []
    for r in range(len(teams) - 1):
        pairs = [(teams[i], teams[-1 - i]) for i in range(len(teams) // 2)]
        rounds.append([(a, b) if r % 2 else (b, a) for a, b in pairs])
        teams = [teams[0], teams[-1]] + teams[1:-1]
    return rounds


def _league_season(league_id, teams, cycles, first_day, slots, rng, fid_start) -> list:
    rows, day = [], pd.Timestamp(first_day, tz='UTC')
    for cycle in range(cycles):
        for rnd in _round_robin(teams):
            for (h, a), slot in zip(rnd, slots):
                h, a = (a, h) if cycle % 2 else (h, a)
                gh, ga = rng.poisson(1.5), rng.poisson(1.1)
                rows.append({
                    'season': 2024, 'league_id': league_id, 'date': day + slot,
                    'home_id': h, 'away_id': a, 'home_name': f'T{h}', 'away_name': f'T{a}',
                    'goals_home': gh, 'goals_away': ga,
                    'xg_home': round(max(gh + rng.normal(0, 0.5), 0.05), 2),
                    'xg_away': round(max(ga + rng.normal(0, 0.5), 0.05), 2),
                })
            day += pd.Timedelta(days=3)
    # numery meczów celowo NIE rosną z datą (jak w API)
    for row, fid in zip(rows, rng.permutation(len(rows)) + fid_start):
        row['fixture_id'] = int(fid)
    return rows


def _season(seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = _league_season(**LEAGUE_A, rng=rng, fid_start=1000) + \
        _league_season(**LEAGUE_B, rng=rng, fid_start=5000)
    # dodatkowy (przełożony) mecz — drużyny 1 i 2 mają o jeden mecz więcej niż reszta ligi A
    rows.append({'fixture_id': 900, 'season': 2024, 'league_id': 39,
                 'date': pd.Timestamp(LEAGUE_A['first_day'], tz='UTC') - pd.Timedelta(days=2),
                 'home_id': 2, 'away_id': 1, 'home_name': 'T2', 'away_name': 'T1',
                 'goals_home': 2, 'goals_away': 2, 'xg_home': 1.7, 'xg_away': 1.1})
    return pd.DataFrame(rows)


@pytest.fixture(scope='module')
def season():
    return _season()


@pytest.fixture(scope='module')
def features(season):
    return build_features(season)


def _oracle_history(season, team_id, date, fixture_id) -> pd.DataFrame:
    """Niezależnie od build_features: występy drużyny przed meczem (date, fixture_id)."""
    s = season.sort_values(['date', 'fixture_id'])
    prior = s[(s['date'] < date) | ((s['date'] == date) & (s['fixture_id'] < fixture_id))]
    recs = []
    for _, m in prior.iterrows():
        if m['home_id'] == team_id:
            gs, gc, xs, xc = m['goals_home'], m['goals_away'], m['xg_home'], m['xg_away']
        elif m['away_id'] == team_id:
            gs, gc, xs, xc = m['goals_away'], m['goals_home'], m['xg_away'], m['xg_home']
        else:
            continue
        recs.append({'xg_scored': xs, 'xg_conceded': xc, 'goals_scored': gs, 'goals_conceded': gc,
                     'won': int(gs > gc), 'drawn': int(gs == gc), 'lost': int(gs < gc),
                     'btts': int(gs > 0 and gc > 0)})
    return pd.DataFrame(recs)


# ---------------------------------------------------------------------------
# build_features — poprawność i brak wycieku
# ---------------------------------------------------------------------------

def test_synthetic_season_has_both_leagues(features):
    assert set(features['league_id']) == {39, 253}


def test_rolling_features_match_independent_calculation(season, features):
    """Cechy drużyny i rywala == średnie policzone wprost z surowych meczów (wyrocznia)."""
    for _, row in features.sample(40, random_state=1).iterrows():
        for team_col, prefix in (('team_id', ''), ('opponent_id', 'opp_')):
            hist = _oracle_history(season, row[team_col], row['date'], row['fixture_id'])
            for n, tag in ((5, 'last5'), (10, 'last10')):
                for stat in FEATURE_STATS:
                    assert row[f'{prefix}{stat}_{tag}'] == pytest.approx(hist.tail(n)[stat].mean()), \
                        (row['fixture_id'], prefix, stat, tag)
        assert row['games_played'] == len(_oracle_history(season, row['team_id'], row['date'],
                                                          row['fixture_id']))
        match = season[season['fixture_id'] == row['fixture_id']].iloc[0]
        side, opp = ('home', 'away') if row['is_home'] else ('away', 'home')
        assert row['team_id'] == match[f'{side}_id'] and row['opponent_id'] == match[f'{opp}_id']
        assert row['team_name'] == match[f'{side}_name']
        assert row['opponent_name'] == match[f'{opp}_name']
        assert row['goals_scored'] == match[f'goals_{side}']
        assert row['goals_conceded'] == match[f'goals_{opp}']


def test_games_played_counts_prior_matches_of_each_team(season, features):
    s = season.sort_values(['date', 'fixture_id']).reset_index(drop=True)
    order = {fid: k for k, fid in enumerate(s['fixture_id'])}
    for _, row in features.iterrows():
        prior = s.iloc[:order[row['fixture_id']]]
        for team_col in ('team_id', 'opponent_id'):
            played = ((prior['home_id'] == row[team_col]) | (prior['away_id'] == row[team_col])).sum()
            assert played >= 10
            if team_col == 'team_id':
                assert row['games_played'] == played, (row['fixture_id'], row['is_home'])
    assert (features.groupby('fixture_id')['games_played'].nunique() > 1).any()   # przypadek nie jest pusty


def test_opponent_features_mirror_team_features(features):
    """opp_* w wierszu drużyny == cechy własne w wierszu rywala tego samego meczu."""
    opp_cols = [c for c in features.columns if c.startswith('opp_')]
    assert opp_cols
    merged = features.merge(features, left_on=['fixture_id', 'opponent_id'],
                            right_on=['fixture_id', 'team_id'], suffixes=('', '_o'))
    assert len(merged) == len(features)
    for c in opp_cols:
        np.testing.assert_allclose(merged[c], merged[c[len('opp_'):] + '_o'], err_msg=c)
    np.testing.assert_allclose(merged['lg_goals_for'], merged['lg_goals_against_o'])
    np.testing.assert_allclose(merged['lg_xg_for'], merged['lg_xg_against_o'])


def test_ten_game_minimum_applies_to_both_teams(season, features):
    assert not features.empty
    assert features['games_played'].min() == 10
    # drużyna z 8 meczami (każdy przeciw drużynie z 10+ meczami) — żaden jej mecz nie daje
    # wierszy, ani gdy gra jako gość, ani jako gospodarz
    late = season['date'].max()
    newcomer = pd.DataFrame([{
        'fixture_id': 990 + k, 'season': 2024, 'league_id': 39,
        'date': late + pd.Timedelta(days=3 * (k + 1)),
        'home_id': 99 if k % 2 else 1 + k % 6, 'away_id': 1 + k % 6 if k % 2 else 99,
        'home_name': 'X', 'away_name': 'Y',
        'goals_home': 1, 'goals_away': 1, 'xg_home': 1.0, 'xg_away': 1.0} for k in range(8)])
    rebuilt = build_features(pd.concat([season, newcomer], ignore_index=True))
    assert not set(newcomer['fixture_id']) & set(rebuilt['fixture_id'])


def test_match_result_does_not_leak_into_its_own_features(season, features):
    """Zmiana wyniku meczu nie zmienia cech tego meczu ani meczów wcześniejszych."""
    target_fid = features['fixture_id'].iloc[len(features) // 2]
    changed = season.copy()
    mask = changed['fixture_id'] == target_fid
    changed.loc[mask, ['goals_home', 'goals_away', 'xg_home', 'xg_away']] = [9, 9, 7.5, 7.5]
    rebuilt = build_features(changed)

    feat_cols = [c for c in features.columns if c not in ('goals_scored', 'goals_conceded')]
    target_date = season.loc[mask, 'date'].iloc[0]
    upto = features['date'] <= target_date
    pd.testing.assert_frame_equal(
        features.loc[upto, feat_cols].reset_index(drop=True),
        rebuilt.loc[rebuilt['date'] <= target_date, feat_cols].reset_index(drop=True))
    # a późniejsze mecze faktycznie widzą zmianę (test nie jest pusty)
    assert not features.loc[~upto, feat_cols].reset_index(drop=True).equals(
        rebuilt.loc[rebuilt['date'] > target_date, feat_cols].reset_index(drop=True))


def test_league_context_uses_only_finished_matches_of_same_league(season, features):
    """lg_* == średnie z meczów TEJ ligi, które zaczęły się >= LEAGUE_CTX_BUFFER wcześniej
    (obejmuje mecze po północy UTC, równoczesne starty i mecz dokładnie na granicy)."""
    for _, row in features.iterrows():
        done = season[(season['league_id'] == row['league_id'])
                      & (season['date'] <= row['date'] - LEAGUE_CTX_BUFFER)]
        side, opp = ('home', 'away') if row['is_home'] else ('away', 'home')
        assert row['lg_matches'] == len(done)
        assert row['lg_goals_for'] == pytest.approx(done[f'goals_{side}'].mean())
        assert row['lg_goals_against'] == pytest.approx(done[f'goals_{opp}'].mean())
        assert row['lg_xg_for'] == pytest.approx(done[f'xg_{side}'].mean())
        assert row['lg_xg_against'] == pytest.approx(done[f'xg_{opp}'].mean())


def test_synthetic_data_contains_match_in_progress_across_utc_midnight(season):
    """Dane syntetyczne muszą zawierać mecz, który reguła 'poprzednie dni UTC' policzyłaby,
    choć jeszcze trwa — inaczej test wyżej nie chroniłby przed tym błędem."""
    in_progress = 0
    for _, m in season.iterrows():
        earlier_utc_day = season[(season['league_id'] == m['league_id'])
                                 & (season['date'].dt.floor('D') < m['date'].floor('D'))]
        in_progress += (earlier_utc_day['date'] > m['date'] - LEAGUE_CTX_BUFFER).sum()
    assert in_progress > 0


def test_league_context_ignores_match_in_progress_across_utc_midnight():
    """Kolejka MLS przez północ UTC: mecz o 00:30 nie widzi meczu z 23:00, który jeszcze trwa;
    mecz innej ligi nie wpływa na kontekst."""
    t = lambda s: pd.Timestamp(s, tz='UTC')
    df = pd.DataFrame({
        'fixture_id': [5, 2, 7, 4, 9],
        'league_id':  [253, 253, 253, 253, 39],
        'date':       [t('2025-06-21 18:00'), t('2025-06-21 23:00'), t('2025-06-22 00:30'),
                       t('2025-06-22 02:30'), t('2025-06-21 12:00')],
        'goals_home': [1, 7, 0, 2, 9], 'goals_away': [0, 0, 0, 2, 9],
        'xg_home':    [1.0, 5.0, 0.5, 1.5, 9.0], 'xg_away': [0.5, 0.1, 0.5, 1.5, 9.0],
    })
    ctx = _league_context(df)
    assert ctx[7]['lg_matches'] == 1 and ctx[7]['lg_goals_home'] == 1.0   # tylko mecz z 18:00
    assert ctx[4]['lg_matches'] == 2 and ctx[4]['lg_goals_home'] == 4.0   # + zakończony z 23:00
    assert np.isnan(ctx[5]['lg_matches']) and np.isnan(ctx[9]['lg_matches'])


def test_impute_xg_uses_same_side_goals():
    df = pd.DataFrame({'goals_home': [3, 1], 'goals_away': [0, 2],
                       'xg_home': [np.nan, 1.4], 'xg_away': [0.2, np.nan]})
    out = impute_xg(df)
    assert out['xg_home'].tolist() == [3, 1.4]
    assert out['xg_away'].tolist() == [0.2, 2]


# ---------------------------------------------------------------------------
# Macierz wyników, rynki, metryki
# ---------------------------------------------------------------------------

def test_score_matrix_without_rho_is_independent_poisson():
    m = score_matrix([1.4], [0.9], rho=0.0)[0]
    g = np.arange(m.shape[0])
    expected = np.outer(poisson.pmf(g, 1.4), poisson.pmf(g, 0.9))
    np.testing.assert_allclose(m, expected / expected.sum())


def test_score_matrix_dixon_coles_cells():
    lh, la, rho = 1.3, 1.1, -0.1
    m = score_matrix([lh], [la], rho)[0]
    base = score_matrix([lh], [la], 0.0)[0]
    # stosunki komórek względem 2:2 (niekorygowanej) usuwają wpływ normalizacji
    ratio = lambda mat, i, j: mat[i, j] / mat[2, 2]
    assert ratio(m, 0, 0) == pytest.approx(ratio(base, 0, 0) * (1 - lh * la * rho))
    assert ratio(m, 1, 0) == pytest.approx(ratio(base, 1, 0) * (1 + la * rho))
    assert ratio(m, 0, 1) == pytest.approx(ratio(base, 0, 1) * (1 + lh * rho))
    assert ratio(m, 1, 1) == pytest.approx(ratio(base, 1, 1) * (1 - rho))


def test_market_probs_match_closed_form():
    p = market_probs(score_matrix([1.4], [0.9], rho=0.0)).iloc[0]
    assert p['p_over25'] == pytest.approx(1 - poisson.cdf(2, 2.3), abs=1e-5)
    assert p['p_btts'] == pytest.approx((1 - np.exp(-1.4)) * (1 - np.exp(-0.9)), abs=1e-5)
    g = np.arange(30)
    joint = np.outer(poisson.pmf(g, 1.4), poisson.pmf(g, 0.9))
    assert p['p_draw'] == pytest.approx(np.trace(joint), abs=1e-5)
    assert p['p_home'] == pytest.approx(np.tril(joint, -1).sum(), abs=1e-5)
    assert p['p_away'] == pytest.approx(np.triu(joint, 1).sum(), abs=1e-5)


def test_market_probs_consistent():
    p = market_probs(score_matrix([0.5, 1.5, 3.0], [2.0, 1.2, 0.4], rho=-0.05))
    np.testing.assert_allclose(p[['p_home', 'p_draw', 'p_away']].sum(axis=1), 1.0)
    assert p['p_home'].is_monotonic_increasing
    assert ((p >= 0) & (p <= 1)).all().all()


def test_market_outcomes_table():
    y = market_outcomes([2, 1, 0, 1, 0, 0, 3], [1, 1, 2, 0, 3, 0, 3])
    expected = pd.DataFrame({
        'p_home':   [1, 0, 0, 1, 0, 0, 0],
        'p_draw':   [0, 1, 0, 0, 0, 1, 1],
        'p_away':   [0, 0, 1, 0, 1, 0, 0],
        'p_over25': [1, 0, 0, 0, 1, 0, 1],
        'p_btts':   [1, 1, 0, 0, 0, 0, 1],
    })
    pd.testing.assert_frame_equal(y[MARKETS], expected)


def test_rps_reference_values():
    p = np.array([[0.5, 0.3, 0.2], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.2, 0.3, 0.5]])
    np.testing.assert_allclose(rps_1x2(p, np.array([0, 2, 1, 1, 0])), [0.145, 1.0, 0.5, 0.0, 0.445])


@pytest.mark.parametrize('gh, ga', [(2, 1), (1, 1), (0, 2), (1, 0), (0, 3), (0, 0)])
def test_match_losses_hand_computed(gh, ga):
    lh, la, rho = 1.6, 0.8, -0.05
    matches = pd.DataFrame({'fixture_id': [1], 'league_id': [39], 'lam_home': [lh],
                            'lam_away': [la], 'goals_home': [gh], 'goals_away': [ga]})
    m = score_matrix([lh], [la], rho)[0]
    p = market_probs(score_matrix([lh], [la], rho)).iloc[0]
    loss = match_losses(matches, rho).iloc[0]

    p1x2 = np.array([p['p_home'], p['p_draw'], p['p_away']])
    k = 0 if gh > ga else (1 if gh == ga else 2)
    onehot = np.eye(3)[k]
    over, btts = int(gh + ga >= 3), int(gh > 0 and ga > 0)
    bin_ll = lambda q, o: -np.log(q if o else 1 - q)
    dev = lambda y, mu: 2 * ((y * np.log(y / mu) if y else 0) - (y - mu))

    assert loss['logloss_1x2'] == pytest.approx(-np.log(p1x2[k]))
    assert loss['rps_1x2'] == pytest.approx(((np.cumsum(p1x2) - np.cumsum(onehot))[:2] ** 2).sum() / 2)
    assert loss['brier_1x2'] == pytest.approx(((p1x2 - onehot) ** 2).sum())
    assert loss['logloss_ou25'] == pytest.approx(bin_ll(p['p_over25'], over))
    assert loss['brier_ou25'] == pytest.approx((p['p_over25'] - over) ** 2)
    assert loss['logloss_btts'] == pytest.approx(bin_ll(p['p_btts'], btts))
    assert loss['brier_btts'] == pytest.approx((p['p_btts'] - btts) ** 2)
    assert loss['score_nll'] == pytest.approx(-np.log(m[gh, ga]))
    assert loss['poisson_dev'] == pytest.approx((dev(gh, lh) + dev(ga, la)) / 2)


@pytest.mark.parametrize('true_rho', [-0.10, 0.08])
def test_fit_rho_recovers_known_value_with_asymmetric_lambdas(true_rho):
    rng = np.random.default_rng(7)
    parts = []
    for lh, la in ((2.2, 0.7), (0.8, 1.9), (1.5, 1.2)):
        m = score_matrix([lh], [la], true_rho)[0]
        cells = rng.choice(m.size, size=10000, p=m.ravel())
        parts.append(pd.DataFrame({'lam_home': lh, 'lam_away': la,
                                   'goals_home': cells // m.shape[1], 'goals_away': cells % m.shape[1]}))
    matches = pd.concat(parts, ignore_index=True)
    rho, se = fit_rho(matches)
    assert 0 < se < 0.03
    assert abs(rho - true_rho) < 2 * se

    # SE z krzywizny == połowa szerokości przedziału z profilu wiarygodności (spadek o 0.5)
    gh, ga = matches['goals_home'].to_numpy(), matches['goals_away'].to_numpy()
    idx = np.arange(len(matches))
    nll = lambda r: -np.log(score_matrix(matches['lam_home'], matches['lam_away'], r)[idx, gh, ga]).sum()
    target = nll(rho) + 0.5
    lo = brentq(lambda r: nll(r) - target, rho - 0.2, rho)
    hi = brentq(lambda r: nll(r) - target, rho, rho + 0.2)
    assert se == pytest.approx((hi - lo) / 2, rel=0.02)


def test_paired_comparison_sign_alignment_and_z():
    ids = [10, 11, 12, 13]
    d = np.array([0.1, 0.3, 0.2, 0.4])
    ref = pd.DataFrame({'fixture_id': ids, **{c: 1.0 for c in LOSSES}})
    worse = pd.DataFrame({'fixture_id': ids, **{c: 1.0 + d for c in LOSSES}}).iloc[::-1]
    diff, z = paired_comparison({'ref': ref, 'worse': worse}, 'ref')
    assert diff.loc['worse', 'logloss_1x2'] == pytest.approx(0.25)                 # model − ref
    assert z.loc['worse', 'logloss_1x2'] == pytest.approx(0.25 / (d.std(ddof=1) / 2))
    assert list(diff.index) == ['worse']


def test_calibration_in_the_large_sign():
    n = 100
    preds = pd.DataFrame({'goals_home': [1, 0] * (n // 2), 'goals_away': [0, 1] * (n // 2),
                          'p_home': 0.6, 'p_draw': 0.1, 'p_away': 0.3, 'p_over25': 0.5, 'p_btts': 0.5})
    c = calibration_in_the_large(preds)
    assert c.loc['p_home', 'predicted'] == pytest.approx(0.6)
    assert c.loc['p_home', 'observed'] == pytest.approx(0.5)
    assert c.loc['p_home', 'z'] == pytest.approx((50 - 60) / np.sqrt(n * 0.24))   # przeszacowanie
    assert c.loc['p_away', 'z'] > 0                                               # niedoszacowanie


def test_calibration_1x2_joint_detects_shift():
    rng = np.random.default_rng(5)
    n = 5000
    p = np.tile([0.45, 0.27, 0.28], (n, 1))
    outcome = rng.choice(3, size=n, p=p[0])
    goals = {0: (1, 0), 1: (1, 1), 2: (0, 1)}
    base = pd.DataFrame({'goals_home': [goals[k][0] for k in outcome],
                         'goals_away': [goals[k][1] for k in outcome]})
    calibrated = base.assign(p_home=p[:, 0], p_draw=p[:, 1], p_away=p[:, 2])
    shifted = base.assign(p_home=0.38, p_draw=0.27, p_away=0.35)
    assert calibration_1x2_joint(calibrated)['p_value'] > 0.01
    assert calibration_1x2_joint(shifted)['p_value'] < 1e-6
    # przy stałych prognozach test == chi² Pearsona dla 3 kategorii (2 stopnie swobody)
    counts = np.bincount(outcome, minlength=3)
    for frame, probs in ((calibrated, p[0]), (shifted, [0.38, 0.27, 0.35])):
        ref = chisquare(counts, f_exp=np.asarray(probs) * n)
        res = calibration_1x2_joint(frame)
        assert res['chi2'] == pytest.approx(ref.statistic)
        assert res['p_value'] == pytest.approx(ref.pvalue)


# ---------------------------------------------------------------------------
# Podział, łączenie wierszy, cechy, wybór modelu
# ---------------------------------------------------------------------------

def test_split_by_time_is_disjoint_ordered_and_respects_boundaries(features):
    df = features.copy()
    fids = sorted(df['fixture_id'].unique())
    k = len(fids)
    # daty rosnące od 2024-06-01 do ~2026-04; trzy mecze dokładnie na granicach podziału
    days = {fid: pd.Timestamp('2024-06-01', tz='UTC') + pd.Timedelta(days=int(i * 700 / k))
            for i, fid in enumerate(fids)}
    before_valid = max(f for f in fids if days[f] < VALID_START)
    at_valid = min(f for f in fids if days[f] >= VALID_START)
    at_test = min(f for f in fids if days[f] >= TEST_START)
    days.update({before_valid: VALID_START - pd.Timedelta(seconds=1),
                 at_valid: VALID_START, at_test: TEST_START})
    df['date'] = df['fixture_id'].map(days)

    train, valid, test = split_by_time(df)
    ids = [set(x['fixture_id']) for x in (train, valid, test)]
    assert not (ids[0] & ids[1]) and not (ids[1] & ids[2]) and not (ids[0] & ids[2])
    assert sum(map(len, ids)) == k
    assert before_valid in ids[0] and at_valid in ids[1] and at_test in ids[2]
    assert train['date'].max() < valid['date'].min() <= valid['date'].max() < test['date'].min()


def test_to_matches_pairs_home_and_away(features):
    lam = np.where(features['is_home'] == 1, 2.0, 1.0)
    m = to_matches(features, lam).set_index('fixture_id')
    assert len(m) == features['fixture_id'].nunique()
    assert (m['lam_home'] == 2.0).all() and (m['lam_away'] == 1.0).all()
    home = features[features['is_home'] == 1].set_index('fixture_id')
    away = features[features['is_home'] == 0].set_index('fixture_id')
    np.testing.assert_array_equal(m.loc[home.index, 'home_name'], home['team_name'])
    np.testing.assert_array_equal(m.loc[away.index, 'away_name'], away['team_name'])
    np.testing.assert_array_equal(m.loc[home.index, 'goals_home'], home['goals_scored'])
    np.testing.assert_array_equal(m.loc[home.index, 'goals_away'], home['goals_conceded'])


def test_feature_columns_exclude_target_and_identifiers(features):
    cols = feature_columns(add_derived_features(features))
    assert not set(cols) & NON_FEATURES
    for leaky in ('goals_scored', 'goals_conceded', 'fixture_id', 'date', 'team_id', 'opponent_id'):
        assert leaky not in cols
    assert 'is_home' in cols and 'exp_xg_last10' in cols and 'lg_goals_for' in cols


def test_derived_features_formulas(features):
    out = add_derived_features(features)
    lg_xg = (out['lg_xg_for'] + out['lg_xg_against']) / 2
    lg_goals = (out['lg_goals_for'] + out['lg_goals_against']) / 2
    for tag in ('last5', 'last10'):
        g = lambda c: out[f'{c}_{tag}']
        np.testing.assert_allclose(g('exp_xg'), g('xg_scored') * g('opp_xg_conceded') / lg_xg)
        np.testing.assert_allclose(g('exp_goals'), g('goals_scored') * g('opp_goals_conceded') / lg_goals)
        np.testing.assert_allclose(g('xg_diff'), g('xg_scored') - g('xg_conceded'))
        np.testing.assert_allclose(g('opp_xg_diff'), g('opp_xg_scored') - g('opp_xg_conceded'))
        np.testing.assert_allclose(g('finishing'), g('goals_scored') - g('xg_scored'))
        np.testing.assert_allclose(g('opp_keeping'), g('opp_goals_conceded') - g('opp_xg_conceded'))
    new = [c for c in out.columns if c not in features.columns]
    assert not out[new].isna().any().any()


def test_oof_lambdas_never_predict_rows_seen_in_training(features):
    trained_on = []

    class Constant:
        def __init__(self, k):
            self.k = k

        def predict(self, X):
            return np.full(len(X), float(self.k))

    def fit(d):
        trained_on.append(set(d['fixture_id']))
        return Constant(len(trained_on) - 1)

    oof = oof_lambdas(fit, features, ['is_home'])
    folds = pd.Series(oof, index=features['fixture_id'].to_numpy())
    assert folds.groupby(level=0).nunique().max() == 1            # oba wiersze meczu w jednym foldzie
    assert set(folds.unique()) == set(range(len(trained_on)))     # każdy wiersz przewidziany
    for k, seen in enumerate(trained_on):
        assert not set(folds[folds == k].index) & seen


def test_blend_and_weight_selection():
    a, b = np.array([1.0, 2.0, 0.5]), np.array([4.0, 2.0, 2.0])
    np.testing.assert_allclose(blend_lambdas(a, b, 1.0), a)
    np.testing.assert_allclose(blend_lambdas(a, b, 0.0), b)
    np.testing.assert_allclose(blend_lambdas(a, b, 0.5), np.sqrt(a * b))
    y = np.array([0, 1, 2, 3, 4, 1, 0, 2])
    assert fit_blend_weight(y, y + 0.05, np.full(len(y), y.mean())) == 1.0
    assert fit_blend_weight(y, np.full(len(y), y.mean()), y + 0.05) == 0.0


def test_league_avg_baseline_uses_own_side(features):
    np.testing.assert_array_equal(league_avg_lambdas(features), features['lg_goals_for'].to_numpy())
