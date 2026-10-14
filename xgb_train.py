"""
xgb_train.py — trening i ewaluacja modelu XGBoost przewidującego liczbę goli drużyny.

Model: regresja Poissona (count:poisson) na wierszach xgb_features (1 mecz = 2 wiersze).
Dwie przewidziane średnie (λ gospodarza, λ gościa) dają macierz wyników z korektą
Dixon-Colesa, a z niej prawdopodobieństwa rynków 1X2, Over/Under 2.5 i BTTS.

Podział wyłącznie po DACIE (oba wiersze meczu zawsze w tym samym zbiorze):
    trening   — mecze przed VALID_START
    walidacja — VALID_START .. TEST_START (early stopping, alpha GLM, waga mieszanki)
    test      — od TEST_START (oceniany raz, na końcu)
Rho Dixon-Colesa każdego modelu: z λ out-of-fold na treningu + λ walidacji (bez testu).

Modele oceniane na tym samym teście:
    xgboost     — model docelowy
    glm         — liniowa regresja Poissona na tych samych cechach (punkt odniesienia)
    blend       — średnia geometryczna λ XGBoost i GLM, waga z walidacji
    old_formula — przybliżenie wzoru z bet_engine.py (mediany zastąpione średnimi z last5)
    league_avg  — średnia goli strony (dom / wyjazd) w lidze, bez wiedzy o drużynach
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.optimize import minimize_scalar
from scipy.special import xlogy
from scipy.stats import chi2, poisson
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_poisson_deviance
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import engine, logger

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
VALID_START = pd.Timestamp('2025-01-01', tz='UTC')
TEST_START  = pd.Timestamp('2025-07-01', tz='UTC')

MODEL_DIR  = Path('models')
MAX_GOALS  = 10                     # macierz wyników 0..9 × 0..9
RHO_BOUNDS = (-0.25, 0.15)
OOF_FOLDS  = 5
GLM_ALPHAS = [1e-4, 1e-3, 1e-2, 1e-1, 1.0]
BLEND_GRID = np.round(np.linspace(0, 1, 21), 2)
REFERENCE_MODEL = 'glm'             # punkt odniesienia w porównaniu parami

XGB_PARAMS = {
    'objective':        'count:poisson',
    'eval_metric':      'poisson-nloglik',
    'max_depth':        3,       # płytkie drzewa — mniej przeuczenia na zaszumionych danych
    'learning_rate':    0.03,
    'min_child_weight': 20,      # min. suma hesjanu w liściu (~7 wierszy przy count:poisson)
    'subsample':        0.8,
    'colsample_bytree': 0.8,
    'reg_lambda':       5,
    'tree_method':      'hist',
    'random_state':     42,
}
N_ESTIMATORS_MAX = 2000
EARLY_STOPPING   = 100

TARGET = 'goals_scored'
NON_FEATURES = {
    'fixture_id', 'date', 'season', 'league_id', 'team_id', 'team_name',
    'opponent_id', 'opponent_name', 'goals_scored', 'goals_conceded',
}
LOSSES = ['poisson_dev', 'logloss_1x2', 'rps_1x2', 'brier_1x2', 'logloss_ou25',
          'brier_ou25', 'logloss_btts', 'brier_btts', 'score_nll']
MARKETS = ['p_home', 'p_draw', 'p_away', 'p_over25', 'p_btts']


# ---------------------------------------------------------------------------
# LOAD + FEATURES
# ---------------------------------------------------------------------------

def load_features() -> pd.DataFrame:
    """Wczytuje tabelę xgb_features zbudowaną przez xgb_model.py."""
    df = pd.read_sql("SELECT * FROM xgb_features", engine, parse_dates=['date'])
    df['date'] = pd.to_datetime(df['date'], utc=True)
    logger.info(f"Załadowano {len(df)} wierszy xgb_features ({df['fixture_id'].nunique()} meczów).")
    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cechy pochodne liczone z cech jednego wiersza — identycznie przy treningu i predykcji."""
    df = df.copy()
    lg_xg    = (df['lg_xg_for'] + df['lg_xg_against']) / 2
    lg_goals = (df['lg_goals_for'] + df['lg_goals_against']) / 2
    for tag in ('last5', 'last10'):
        # siła ataku × słabość obrony rywala, znormalizowane do średniej ligi
        df[f'exp_xg_{tag}']    = df[f'xg_scored_{tag}'] * df[f'opp_xg_conceded_{tag}'] / lg_xg
        df[f'exp_goals_{tag}'] = df[f'goals_scored_{tag}'] * df[f'opp_goals_conceded_{tag}'] / lg_goals
        df[f'xg_diff_{tag}']     = df[f'xg_scored_{tag}'] - df[f'xg_conceded_{tag}']
        df[f'opp_xg_diff_{tag}'] = df[f'opp_xg_scored_{tag}'] - df[f'opp_xg_conceded_{tag}']
        # skuteczność: gole ponad / poniżej xG (wartości dodatnie zwykle regresują)
        df[f'finishing_{tag}']   = df[f'goals_scored_{tag}'] - df[f'xg_scored_{tag}']
        df[f'opp_keeping_{tag}'] = df[f'opp_goals_conceded_{tag}'] - df[f'opp_xg_conceded_{tag}']
    return df


def feature_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in NON_FEATURES]


def split_by_time(df: pd.DataFrame):
    """Podział po dacie meczu — oba wiersze meczu mają tę samą datę, więc trafiają razem."""
    train = df[df['date'] < VALID_START]
    valid = df[(df['date'] >= VALID_START) & (df['date'] < TEST_START)]
    test  = df[df['date'] >= TEST_START]
    for name, part in (('trening', train), ('walidacja', valid), ('test', test)):
        logger.info(f"  {name:<9}: {part['fixture_id'].nunique():>5} meczów "
                    f"({part['date'].min():%Y-%m-%d} – {part['date'].max():%Y-%m-%d})")
    return train, valid, test


# ---------------------------------------------------------------------------
# MODELE — każdy zwraca λ = oczekiwana liczba goli drużyny w wierszu
# ---------------------------------------------------------------------------

def train_xgb(train: pd.DataFrame, valid: pd.DataFrame, features: list):
    """Trening z early stoppingiem na walidacji. Zwraca model (predict używa best_iteration)."""
    model = xgb.XGBRegressor(**XGB_PARAMS, n_estimators=N_ESTIMATORS_MAX,
                             early_stopping_rounds=EARLY_STOPPING)
    model.fit(train[features], train[TARGET],
              eval_set=[(valid[features], valid[TARGET])], verbose=False)
    logger.info(f"XGBoost: best_iteration = {model.best_iteration}")
    return model


def fit_xgb(df: pd.DataFrame, features: list, n_rounds: int):
    """XGBoost ze stałą liczbą drzew (wyznaczoną wcześniej przez early stopping)."""
    model = xgb.XGBRegressor(**XGB_PARAMS, n_estimators=n_rounds)
    model.fit(df[features], df[TARGET], verbose=False)
    return model


def fit_glm(df: pd.DataFrame, features: list, alpha: float):
    model = make_pipeline(StandardScaler(), PoissonRegressor(alpha=alpha, max_iter=1000))
    model.fit(df[features], df[TARGET])
    return model


def select_glm_alpha(train: pd.DataFrame, valid: pd.DataFrame, features: list):
    """Dobiera alpha GLM na walidacji. Zwraca (alpha, λ walidacji z modelu uczonego na treningu)."""
    best = None
    for alpha in GLM_ALPHAS:
        pred = fit_glm(train, features, alpha).predict(valid[features])
        dev = mean_poisson_deviance(valid[TARGET], pred)
        if best is None or dev < best[0]:
            best = (dev, alpha, pred)
    logger.info(f"GLM: alpha = {best[1]}")
    return best[1], best[2]


def oof_lambdas(fit, train: pd.DataFrame, features: list) -> np.ndarray:
    """λ out-of-fold dla treningu (GroupKFold po meczu) — do estymacji rho bez optymizmu
    predykcji na danych, na których model się uczył."""
    oof = np.empty(len(train))
    for fit_idx, pred_idx in GroupKFold(n_splits=OOF_FOLDS).split(train, groups=train['fixture_id']):
        oof[pred_idx] = fit(train.iloc[fit_idx]).predict(train.iloc[pred_idx][features])
    return oof


def blend_lambdas(lam_xgb, lam_glm, w: float) -> np.ndarray:
    """Średnia geometryczna λ (średnia ważona w skali log, w której działa model Poissona)."""
    return np.exp(w * np.log(lam_xgb) + (1 - w) * np.log(lam_glm))


def fit_blend_weight(y, lam_xgb, lam_glm) -> float:
    """Waga XGBoost w mieszance minimalizująca dewiancję Poissona na walidacji."""
    devs = [mean_poisson_deviance(y, blend_lambdas(lam_xgb, lam_glm, w)) for w in BLEND_GRID]
    return float(BLEND_GRID[int(np.argmin(devs))])


def league_avg_lambdas(df: pd.DataFrame) -> np.ndarray:
    """Punkt odniesienia bez wiedzy o drużynach: średnia goli tej strony w lidze."""
    return df['lg_goals_for'].to_numpy()


def old_formula_lambdas(df: pd.DataFrame) -> np.ndarray:
    """
    Przybliżenie wzoru z bet_engine.py na tych samych danych. Różnice: mediany goli
    zastąpione średnimi (waga 0.25 + 0.20 → 0.45), średnie ligi z bieżącego sezonu
    zamiast z ostatnich ~5 kolejek.
    """
    raw_att     = df['xg_scored_last5'] * 0.55 + df['goals_scored_last5'] * 0.45
    raw_opp_def = df['opp_xg_conceded_last5'] * 0.55 + df['opp_goals_conceded_last5'] * 0.45
    perf_for     = (df['lg_goals_for'] + df['lg_xg_for']) / 2
    perf_against = (df['lg_goals_against'] + df['lg_xg_against']) / 2
    avg_total    = (perf_for + perf_against) / 2

    lam = (raw_att / avg_total) * (raw_opp_def / avg_total) * perf_for

    luck         = df['goals_scored_last5'] - df['xg_scored_last5']
    opp_def_luck = df['opp_goals_conceded_last5'] - df['opp_xg_conceded_last5']
    form_pts     = (df['won_last5'] * 3 + df['drawn_last5']) * 5
    lam = (lam + opp_def_luck * 0.10 - luck * 0.18) * (0.88 + form_pts / 15 * 0.24)
    return lam.clip(lower=0.01).to_numpy()


# ---------------------------------------------------------------------------
# MACIERZ WYNIKÓW I RYNKI
# ---------------------------------------------------------------------------

def score_matrix(lam_home, lam_away, rho: float) -> np.ndarray:
    """Macierze (n × MAX_GOALS × MAX_GOALS) P(i goli gospodarza, j goli gościa)
    z niezależnych rozkładów Poissona z korektą Dixon-Colesa dla wyników 0:0, 1:0, 0:1, 1:1."""
    lh = np.clip(np.asarray(lam_home, dtype=float), 0.01, None)
    la = np.clip(np.asarray(lam_away, dtype=float), 0.01, None)
    goals = np.arange(MAX_GOALS)
    m = poisson.pmf(goals[None, :, None], lh[:, None, None]) * \
        poisson.pmf(goals[None, None, :], la[:, None, None])

    m[:, 0, 0] *= 1 - lh * la * rho
    m[:, 1, 0] *= 1 + la * rho
    m[:, 0, 1] *= 1 + lh * rho
    m[:, 1, 1] *= 1 - rho

    m = np.clip(m, 0, None)
    return m / m.sum(axis=(1, 2), keepdims=True)


def market_probs(m: np.ndarray) -> pd.DataFrame:
    """Sumuje komórki macierzy wyników w prawdopodobieństwa rynków."""
    i, j = np.indices(m.shape[1:])
    cell = lambda mask: (m * mask).sum(axis=(1, 2))
    return pd.DataFrame({
        'p_home':   cell(i > j),
        'p_draw':   cell(i == j),
        'p_away':   cell(i < j),
        'p_over25': cell(i + j >= 3),
        'p_btts':   cell((i >= 1) & (j >= 1)),
    })


def market_outcomes(goals_home, goals_away) -> pd.DataFrame:
    """Wynik (0/1) każdego rynku z MARKETS dla podanych wyników meczów."""
    gh, ga = np.asarray(goals_home), np.asarray(goals_away)
    return pd.DataFrame({
        'p_home':   gh > ga,
        'p_draw':   gh == ga,
        'p_away':   gh < ga,
        'p_over25': gh + ga >= 3,
        'p_btts':   (gh > 0) & (ga > 0),
    }).astype(int)


def to_matches(rows: pd.DataFrame, lam: np.ndarray) -> pd.DataFrame:
    """Łączy 2 wiersze meczu (gospodarz, gość) w 1 wiersz z λ obu drużyn i wynikiem."""
    r = rows[['fixture_id', 'date', 'league_id', 'team_name', 'is_home', TARGET]].assign(lam=lam)
    home = r[r['is_home'] == 1].set_index('fixture_id')
    away = r[r['is_home'] == 0].set_index('fixture_id')[['team_name', TARGET, 'lam']]
    m = home.drop(columns='is_home').join(away, rsuffix='_away', how='inner')
    return m.rename(columns={
        'team_name': 'home_name', 'team_name_away': 'away_name',
        TARGET: 'goals_home', f'{TARGET}_away': 'goals_away',
        'lam': 'lam_home', 'lam_away': 'lam_away',
    }).reset_index()


def _score_index(matches: pd.DataFrame):
    gh = matches['goals_home'].clip(upper=MAX_GOALS - 1).to_numpy(dtype=int)
    ga = matches['goals_away'].clip(upper=MAX_GOALS - 1).to_numpy(dtype=int)
    return gh, ga


def fit_rho(matches: pd.DataFrame):
    """Rho Dixon-Colesa maksymalizujące wiarygodność dokładnych wyników.
    Zwraca (rho, błąd standardowy z krzywizny log-wiarygodności)."""
    gh, ga = _score_index(matches)
    idx = np.arange(len(matches))
    lh, la = matches['lam_home'].to_numpy(), matches['lam_away'].to_numpy()

    def nll(rho):
        return -np.log(np.maximum(score_matrix(lh, la, rho)[idx, gh, ga], 1e-15)).sum()

    # zawężenie przedziału tak, by korekty tau (1 + λρ, 1 − λhλaρ) były dodatnie dla każdego meczu
    lo = max(RHO_BOUNDS[0], -0.99 / max(lh.max(), la.max()))
    hi = min(RHO_BOUNDS[1], 0.99 / (lh * la).max())
    rho = minimize_scalar(nll, bounds=(lo, hi), method='bounded', options={'xatol': 1e-4}).x
    if min(rho - lo, hi - rho) < 1e-3:
        logger.warning(f"fit_rho: estymata {rho:.4f} na granicy przedziału ({lo:.3f}, {hi:.3f}).")
    h = 1e-3
    curvature = (nll(rho + h) - 2 * nll(rho) + nll(rho - h)) / h ** 2
    se = 1 / np.sqrt(curvature) if curvature > 0 else np.nan
    return float(rho), float(se)


# ---------------------------------------------------------------------------
# EWALUACJA
# ---------------------------------------------------------------------------

def rps_1x2(p1x2: np.ndarray, outcome: np.ndarray) -> np.ndarray:
    """Ranked Probability Score per mecz — standard dla 1X2: remis leży "pomiędzy" wygranymi.
    outcome: 0 = gospodarz, 1 = remis, 2 = gość."""
    onehot = np.eye(3)[outcome]
    return ((np.cumsum(p1x2, axis=1) - np.cumsum(onehot, axis=1))[:, :2] ** 2).sum(axis=1) / 2


def _poisson_unit_deviance(y, mu) -> np.ndarray:
    y, mu = np.asarray(y, dtype=float), np.asarray(mu, dtype=float)
    return 2 * (xlogy(y, y / mu) - (y - mu))


def match_losses(matches: pd.DataFrame, rho: float) -> pd.DataFrame:
    """Straty per mecz (niżej = lepiej). Średnia kolumny daje metrykę modelu, a różnice
    strat dwóch modeli na tych samych meczach — test, czy przewaga nie jest przypadkiem."""
    m = score_matrix(matches['lam_home'], matches['lam_away'], rho)
    p = market_probs(m)
    y = market_outcomes(matches['goals_home'], matches['goals_away'])
    gh, ga = _score_index(matches)
    idx = np.arange(len(matches))
    log = lambda x: np.log(np.clip(x, 1e-15, 1))

    p1x2 = p[['p_home', 'p_draw', 'p_away']].to_numpy()
    outcome = np.select([y['p_home'] == 1, y['p_draw'] == 1], [0, 1], 2)

    def binary(market):
        q, o = p[market].to_numpy(), y[market].to_numpy()
        return -(o * log(q) + (1 - o) * log(1 - q)), (q - o) ** 2

    ll_ou, br_ou = binary('p_over25')
    ll_btts, br_btts = binary('p_btts')
    return pd.DataFrame({
        'fixture_id':   matches['fixture_id'].to_numpy(),
        'league_id':    matches['league_id'].to_numpy(),
        # średnia z 2 wierszy meczu — średnia po meczach = dewiancja na poziomie wierszy
        'poisson_dev':  (_poisson_unit_deviance(matches['goals_home'], matches['lam_home'])
                         + _poisson_unit_deviance(matches['goals_away'], matches['lam_away'])) / 2,
        'logloss_1x2':  -log(p1x2[idx, outcome]),
        'rps_1x2':      rps_1x2(p1x2, outcome),
        'brier_1x2':    ((p1x2 - np.eye(3)[outcome]) ** 2).sum(axis=1),
        'logloss_ou25': ll_ou,
        'brier_ou25':   br_ou,
        'logloss_btts': ll_btts,
        'brier_btts':   br_btts,
        'score_nll':    -log(m[idx, gh, ga]),
    })


def paired_comparison(losses: dict, reference: str):
    """Średnia różnica strat (model − reference) na tych samych meczach i jej z = różnica / SE.
    Ujemna różnica = model lepszy; |z| > 2 ≈ różnica raczej nieprzypadkowa."""
    ref = losses[reference].set_index('fixture_id')[LOSSES]
    diff, z = {}, {}
    for name, loss in losses.items():
        if name == reference:
            continue
        d = loss.set_index('fixture_id')[LOSSES] - ref
        diff[name] = d.mean()
        z[name] = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    return pd.DataFrame(diff).T, pd.DataFrame(z).T


def _calibration_z(p, y) -> float:
    """z = (trafienia − Σp) / sqrt(Σ p(1−p)); ujemne = model przeszacowuje."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return (y.sum() - p.sum()) / np.sqrt((p * (1 - p)).sum())


def calibration_in_the_large(preds: pd.DataFrame) -> pd.DataFrame:
    """Średnie przewidziane prawdopodobieństwo vs częstość dla każdego rynku, z wartością z."""
    y = market_outcomes(preds['goals_home'], preds['goals_away'])
    return pd.DataFrame({mk: {'predicted': preds[mk].mean(), 'observed': y[mk].mean(),
                              'z': _calibration_z(preds[mk], y[mk])} for mk in MARKETS}).T


def calibration_1x2_joint(preds: pd.DataFrame) -> dict:
    """Łączny test kalibracji 1X2 (chi² o 2 stopniach swobody) — p_home, p_draw i p_away
    sumują się do 1, więc ich trzy wartości z nie są niezależne."""
    y = market_outcomes(preds['goals_home'], preds['goals_away'])[['p_home', 'p_draw']].to_numpy()
    p = preds[['p_home', 'p_draw']].to_numpy()
    resid = (y - p).sum(axis=0)
    cov = np.diag(p.sum(axis=0)) - p.T @ p          # Σ_k [diag(p_k) − p_k p_kᵀ]
    stat = float(resid @ np.linalg.solve(cov, resid))
    return {'chi2': stat, 'p_value': float(chi2.sf(stat, df=2))}


def calibration_table(p, y, n_bins: int = 10) -> pd.DataFrame:
    """Przewidziane prawdopodobieństwo vs rzeczywista częstość w przedziałach kwantylowych
    (każdy przedział ma ~tyle samo meczów), z wartością z dla każdego przedziału."""
    t = pd.DataFrame({'p': np.asarray(p, dtype=float), 'y': np.asarray(y, dtype=float)})
    t['bin'] = pd.qcut(t['p'], n_bins, labels=False, duplicates='drop') + 1
    rows = {b: {'n': len(g), 'predicted': g['p'].mean(), 'observed': g['y'].mean(),
                'z': _calibration_z(g['p'], g['y'])} for b, g in t.groupby('bin')}
    return pd.DataFrame(rows).T.rename_axis('decyl')


def match_predictions(matches: pd.DataFrame, rho: float) -> pd.DataFrame:
    """Mecze z λ, prawdopodobieństwami rynków i wynikiem — do raportu i późniejszego backtestu."""
    p = market_probs(score_matrix(matches['lam_home'], matches['lam_away'], rho))
    return pd.concat([matches.reset_index(drop=True), p.round(4)], axis=1)


# ---------------------------------------------------------------------------
# RAPORT + ZAPIS
# ---------------------------------------------------------------------------

def _log_table(title: str, table) -> None:
    logger.info(f"\n=== {title} ===\n" + table.to_string())


def report(summary_valid, summary_test, diff, z, per_league, calib, calib_joint, preds, importance):
    _log_table("WALIDACJA — średnie straty (podstawa wyboru, niżej = lepiej)", summary_valid.round(4))
    _log_table("TEST — średnie straty (niżej = lepiej)", summary_test.round(4))
    paired = diff.map('{:+.4f}'.format) + ' (z=' + z.map('{:+.1f}'.format) + ')'
    _log_table(f"TEST — różnica względem '{REFERENCE_MODEL}' parami (ujemna = lepiej niż "
               f"{REFERENCE_MODEL}; |z| > 2 = raczej nie przypadek)",
               paired[['poisson_dev', 'logloss_1x2', 'rps_1x2', 'logloss_ou25', 'logloss_btts', 'score_nll']])
    _log_table("TEST — logloss 1X2 per liga", per_league.round(4))
    _log_table("TEST — kalibracja ogólna (ujemne z = model przeszacowuje; |z| > 2 = sygnał "
               "do sprawdzenia)", calib.round(3))
    _log_table("TEST — łączny test kalibracji 1X2 (p_value < 0.05 = 1X2 systematycznie przesunięte)",
               pd.DataFrame(calib_joint).T.round(3))

    for mk in MARKETS:
        tables = {}
        for name, p in preds.items():
            y = market_outcomes(p['goals_home'], p['goals_away'])[mk]
            tables[name] = calibration_table(p[mk], y)[['predicted', 'observed', 'z']]
        _log_table(f"TEST — kalibracja w decylach, {mk}", pd.concat(tables, axis=1).round(3))

    top = importance.head(15)
    _log_table("Ważność cech XGBoost (udział w łącznym zysku podziałów, top 15)",
               pd.DataFrame({'share': (top['share'] * 100).round(1).astype(str) + '%',
                             'splits': top['splits'].astype(int)}))


def save_artifacts(xgb_model, glm_model, meta: dict, preds: dict) -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    xgb_model.save_model(MODEL_DIR / 'xgb_goals.json')
    joblib.dump(glm_model, MODEL_DIR / 'glm_goals.joblib')
    (MODEL_DIR / 'xgb_goals_meta.json').write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    pd.concat(preds, names=['model']).reset_index(level=0).to_csv(
        MODEL_DIR / 'test_predictions.csv', index=False, sep=';', encoding='utf-8')
    logger.info(f"Zapisano modele (XGBoost, GLM), metadane i predykcje testowe w '{MODEL_DIR}/'.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    df = add_derived_features(load_features())
    features = feature_columns(df)
    logger.info(f"Cech: {len(features)}. Podział czasowy:")
    train, valid, test = split_by_time(df)
    train_valid = pd.concat([train, valid])

    # XGBoost: early stopping na walidacji, finalnie refit na train + valid
    xgb_es = train_xgb(train, valid, features)
    n_rounds = xgb_es.best_iteration + 1
    xgb_final = fit_xgb(train_valid, features, n_rounds)

    # GLM: alpha z walidacji, finalnie refit na train + valid
    alpha, glm_valid = select_glm_alpha(train, valid, features)
    glm_final = fit_glm(train_valid, features, alpha)

    # λ per model: 'oof' (trening, tylko do rho), 'valid', 'test'
    lambdas = {
        'xgboost': {
            'oof':   oof_lambdas(lambda d: fit_xgb(d, features, n_rounds), train, features),
            'valid': xgb_es.predict(valid[features]),
            'test':  xgb_final.predict(test[features]),
        },
        'glm': {
            'oof':   oof_lambdas(lambda d: fit_glm(d, features, alpha), train, features),
            'valid': glm_valid,
            'test':  glm_final.predict(test[features]),
        },
    }
    blend_w = fit_blend_weight(valid[TARGET], lambdas['xgboost']['valid'], lambdas['glm']['valid'])
    logger.info(f"Mieszanka: waga XGBoost = {blend_w}")
    lambdas['blend'] = {part: blend_lambdas(lambdas['xgboost'][part], lambdas['glm'][part], blend_w)
                        for part in ('oof', 'valid', 'test')}
    parts = (('oof', train), ('valid', valid), ('test', test))
    lambdas['old_formula'] = {part: old_formula_lambdas(d) for part, d in parts}
    lambdas['league_avg']  = {part: league_avg_lambdas(d) for part, d in parts}

    rhos, losses_valid, losses_test, test_matches = {}, {}, {}, {}
    for name, lam in lambdas.items():
        valid_matches = to_matches(valid, lam['valid'])
        rhos[name] = fit_rho(pd.concat([to_matches(train, lam['oof']), valid_matches]))
        test_matches[name] = to_matches(test, lam['test'])
        losses_valid[name] = match_losses(valid_matches, rhos[name][0])
        losses_test[name] = match_losses(test_matches[name], rhos[name][0])

    summarize = lambda losses: pd.DataFrame({n: l[LOSSES].mean() for n, l in losses.items()}).T
    summary_valid = summarize(losses_valid)
    summary_test = summarize(losses_test)
    summary_test.insert(0, 'rho', [rhos[n][0] for n in summary_test.index])
    summary_test.insert(1, 'rho_se', [rhos[n][1] for n in summary_test.index])
    diff, z = paired_comparison(losses_test, REFERENCE_MODEL)

    per_league = pd.DataFrame({n: l.groupby('league_id')['logloss_1x2'].mean()
                               for n, l in losses_test.items()})
    per_league['n'] = losses_test['xgboost'].groupby('league_id').size()

    preds = {n: match_predictions(test_matches[n], rhos[n][0]) for n in ('xgboost', 'glm', 'blend')}
    calib = pd.concat({n: calibration_in_the_large(p) for n, p in preds.items()})
    calib_joint = {n: calibration_1x2_joint(p) for n, p in preds.items()}

    booster = xgb_final.get_booster()
    importance = pd.DataFrame({
        'share':  pd.Series(booster.get_score(importance_type='total_gain')),
        'splits': pd.Series(booster.get_score(importance_type='weight')),
    })
    importance['share'] /= importance['share'].sum()
    importance = importance.sort_values('share', ascending=False)

    report(summary_valid, summary_test, diff, z, per_league, calib, calib_joint, preds, importance)

    save_artifacts(xgb_final, glm_final, {
        'trained_at':  datetime.now(timezone.utc).isoformat(),
        'target':      TARGET,
        'features':    features,
        'xgb_params':  XGB_PARAMS,
        'n_rounds':    n_rounds,
        'glm_alpha':   alpha,
        'blend_w_xgb': blend_w,
        'rho':         {n: {'rho': r, 'se': se} for n, (r, se) in rhos.items()},
        'valid_start': VALID_START,
        'test_start':  TEST_START,
        'n_matches':   {'train': train['fixture_id'].nunique(),
                        'valid': valid['fixture_id'].nunique(),
                        'test':  test['fixture_id'].nunique()},
        'valid_metrics': summary_valid.round(5).to_dict(orient='index'),
        'test_metrics':  summary_test.round(5).to_dict(orient='index'),
        f'test_diff_vs_{REFERENCE_MODEL}': diff.round(5).to_dict(orient='index'),
        f'test_z_vs_{REFERENCE_MODEL}':    z.round(2).to_dict(orient='index'),
    }, preds)


if __name__ == '__main__':
    main()
