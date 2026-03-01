"""
Testy ETL – weryfikują czyste funkcje Transform (bez połączenia z bazą danych / API).
Uruchomienie: pytest tests/test_etl.py -v
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

# Dodajemy katalog główny projektu do ścieżki
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# FIXTURES (dane wspólne dla testów)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_fixtures_df():
    """Minimalny DataFrame meczów do testów."""
    return pd.DataFrame({
        'fixture_id':   [1, 2, 3, 4, 5, 6],
        'date':         ['2025-01-01', '2025-01-08', '2025-01-15',
                         '2025-01-22', '2025-01-29', '2025-02-05'],
        'league_id':    [39, 39, 39, 78, 78, 78],
        'league_name':  ['PL', 'PL', 'PL', 'BL', 'BL', 'BL'],
        'home_id':      [10, 10, 20, 30, 30, 40],
        'home_name':    ['A', 'A', 'B', 'C', 'C', 'D'],
        'away_id':      [20, 30, 10, 40, 40, 30],
        'away_name':    ['B', 'C', 'A', 'D', 'D', 'C'],
        'goals_home':   [2,  1,  1,  3,  0,  2],
        'goals_away':   [1,  0,  2,  1,  1,  2],
        'xg_home':      [1.8, 1.2, 1.0, 2.5, 0.8, 1.5],
        'xg_away':      [0.9, 0.5, 1.5, 0.8, 1.3, 1.5],
        'winner_id':    [10, 10, 20, 30, 40, 0],
        'round_number': [1,  2,  3,  1,  2,  3],
    })


# ===========================================================================
# TESTY: main.py
# ===========================================================================

class TestTransformTeams:
    def test_returns_dataframe(self):
        from main import transform_teams
        raw = [
            {'team': {'id': 1, 'name': 'FC Test', 'code': 'FCT', 'country': 'PL', 'founded': 2000},
             'venue': {'name': 'Test Arena', 'city': 'Warsaw'}}
        ]
        df = transform_teams(raw, 39, 'Premier League')
        assert isinstance(df, pd.DataFrame)

    def test_correct_columns(self):
        from main import transform_teams
        raw = [
            {'team': {'id': 1, 'name': 'FC Test', 'code': 'FCT', 'country': 'PL', 'founded': 2000},
             'venue': {'name': 'Arena', 'city': 'Warsaw'}}
        ]
        df = transform_teams(raw, 39, 'Premier League')
        expected = {'team_id', 'name', 'code', 'country', 'founded',
                    'stadium_name', 'stadium_city', 'league_id', 'league_name'}
        assert expected.issubset(set(df.columns))

    def test_league_id_propagated(self):
        from main import transform_teams
        raw = [
            {'team': {'id': 5, 'name': 'X', 'code': 'X', 'country': 'DE', 'founded': 1900},
             'venue': {'name': 'Y', 'city': 'Berlin'}}
        ]
        df = transform_teams(raw, 78, 'Bundesliga')
        assert df.iloc[0]['league_id'] == 78
        assert df.iloc[0]['league_name'] == 'Bundesliga'
        assert df.iloc[0]['team_id'] == 5

    def test_multiple_teams(self):
        from main import transform_teams
        raw = [
            {'team': {'id': i, 'name': f'T{i}', 'code': f'T{i}', 'country': 'PL', 'founded': 2000},
             'venue': {'name': f'A{i}', 'city': 'Warsaw'}}
            for i in range(5)
        ]
        df = transform_teams(raw, 39, 'PL')
        assert len(df) == 5

    def test_missing_venue_fields_handled(self):
        from main import transform_teams
        raw = [{'team': {'id': 1, 'name': 'T', 'code': 'T', 'country': 'PL', 'founded': None},
                'venue': {}}]
        df = transform_teams(raw, 39, 'PL')
        assert df.iloc[0]['stadium_name'] is None
        assert df.iloc[0]['stadium_city'] is None


# ===========================================================================
# TESTY: upcoming_odds.py
# ===========================================================================

class TestCalculateFairOdds:
    def test_removes_margin_1x2(self):
        from upcoming_odds import calculate_fair_odds
        odds = {'odd_home': 2.0, 'odd_draw': 3.5, 'odd_away': 4.0}
        result = calculate_fair_odds(odds)
        total_prob = 1/result['odd_home'] + 1/result['odd_draw'] + 1/result['odd_away']
        assert abs(total_prob - 1.0) < 0.001

    def test_removes_margin_ou(self):
        from upcoming_odds import calculate_fair_odds
        odds = {'odd_over_25': 1.8, 'odd_under_25': 2.1}
        result = calculate_fair_odds(odds)
        total_prob = 1/result['odd_over_25'] + 1/result['odd_under_25']
        assert abs(total_prob - 1.0) < 0.001

    def test_removes_margin_btts(self):
        from upcoming_odds import calculate_fair_odds
        odds = {'odd_btts_yes': 1.9, 'odd_btts_no': 2.0}
        result = calculate_fair_odds(odds)
        total_prob = 1/result['odd_btts_yes'] + 1/result['odd_btts_no']
        assert abs(total_prob - 1.0) < 0.001

    def test_does_not_mutate_input(self):
        from upcoming_odds import calculate_fair_odds
        original_home = 2.0
        odds = {'odd_home': original_home, 'odd_draw': 3.5, 'odd_away': 4.0}
        calculate_fair_odds(odds)
        assert odds['odd_home'] == original_home  # oryginał bez zmian

    def test_zero_odds_not_processed(self):
        from upcoming_odds import calculate_fair_odds
        odds = {'odd_home': 0, 'odd_draw': 0, 'odd_away': 0}
        result = calculate_fair_odds(odds)
        assert result['odd_home'] == 0  # zerowe kursy zostają bez zmian

    def test_fair_odds_always_higher(self):
        from upcoming_odds import calculate_fair_odds
        odds = {'odd_home': 2.0, 'odd_draw': 3.5, 'odd_away': 4.0}
        result = calculate_fair_odds(odds)
        # usunięcie marży → implied prob maleje → kursy rosną
        assert result['odd_home'] >= 2.0
        assert result['odd_draw'] >= 3.5
        assert result['odd_away'] >= 4.0


class TestTransformApplyFairOdds:
    def test_returns_dict_same_keys(self):
        from upcoming_odds import transform_apply_fair_odds
        raw = {
            123: {'odd_home': 2.0, 'odd_draw': 3.5, 'odd_away': 4.0,
                  'odd_over_25': 1.8, 'odd_under_25': 2.1,
                  'odd_btts_yes': 1.9, 'odd_btts_no': 2.0, 'source_bm': 'Test'},
            456: {'odd_home': 1.5, 'odd_draw': 4.0, 'odd_away': 6.0,
                  'odd_over_25': 0, 'odd_under_25': 0,
                  'odd_btts_yes': 0, 'odd_btts_no': 0, 'source_bm': 'Test'},
        }
        result = transform_apply_fair_odds(raw)
        assert set(result.keys()) == {123, 456}

    def test_does_not_mutate_input(self):
        from upcoming_odds import transform_apply_fair_odds
        raw = {99: {'odd_home': 2.0, 'odd_draw': 3.5, 'odd_away': 4.0,
                    'odd_over_25': 0, 'odd_under_25': 0,
                    'odd_btts_yes': 0, 'odd_btts_no': 0, 'source_bm': 'X'}}
        transform_apply_fair_odds(raw)
        assert raw[99]['odd_home'] == 2.0  # oryginał bez zmian

    def test_empty_input(self):
        from upcoming_odds import transform_apply_fair_odds
        assert transform_apply_fair_odds({}) == {}


# ===========================================================================
# TESTY: fixtures_collector.py
# ===========================================================================

class TestTransformL5Stats:
    def test_returns_dataframe(self, sample_fixtures_df):
        from fixtures_collector import transform_l5_stats
        result = transform_l5_stats(sample_fixtures_df)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns(self, sample_fixtures_df):
        from fixtures_collector import transform_l5_stats
        result = transform_l5_stats(sample_fixtures_df)
        required = {'team_id', 'avg_goals_scored', 'avg_goals_conceded',
                    'avg_xg_for', 'avg_xg_against', 'total_points_l5',
                    'luck_factor', 'defense_luck_factor'}
        assert required.issubset(set(result.columns))

    def test_median_columns_present(self, sample_fixtures_df):
        from fixtures_collector import transform_l5_stats
        result = transform_l5_stats(sample_fixtures_df)
        assert 'med_goals_scored' in result.columns
        assert 'med_goals_conceded' in result.columns

    def test_no_database_call(self, sample_fixtures_df, monkeypatch):
        """Transformacja nie powinna dotykać bazy danych."""
        from fixtures_collector import transform_l5_stats
        import fixtures_collector as fc
        called = []
        monkeypatch.setattr(fc, 'engine', type('E', (), {'connect': lambda *a: called.append(1)})())
        transform_l5_stats(sample_fixtures_df)
        assert len(called) == 0

    def test_points_win_gives_3(self):
        from fixtures_collector import transform_l5_stats
        # Drużyna 10 wygrywa wszystkie mecze
        df = pd.DataFrame({
            'fixture_id': [1, 2, 3, 4, 5],
            'date': ['2025-01-01', '2025-01-08', '2025-01-15', '2025-01-22', '2025-01-29'],
            'league_id': [39]*5, 'league_name': ['PL']*5,
            'home_id': [10]*5, 'home_name': ['A']*5,
            'away_id': [20]*5, 'away_name': ['B']*5,
            'goals_home': [2]*5, 'goals_away': [0]*5,
            'xg_home': [1.5]*5, 'xg_away': [0.8]*5,
            'winner_id': [10]*5,
            'round_number': [1, 2, 3, 4, 5],
        })
        result = transform_l5_stats(df)
        team_10 = result[result['team_id'] == 10].iloc[0]
        assert team_10['total_points_l5'] == 15  # 5 wygranych × 3 pkt

    def test_draw_gives_1_point(self):
        from fixtures_collector import transform_l5_stats
        df = pd.DataFrame({
            'fixture_id': [1],
            'date': ['2025-01-01'],
            'league_id': [39], 'league_name': ['PL'],
            'home_id': [10], 'home_name': ['A'],
            'away_id': [20], 'away_name': ['B'],
            'goals_home': [1], 'goals_away': [1],
            'xg_home': [1.0], 'xg_away': [1.0],
            'winner_id': [0],  # remis = 0
            'round_number': [1],
        })
        result = transform_l5_stats(df)
        team_10 = result[result['team_id'] == 10].iloc[0]
        assert team_10['total_points_l5'] == 1

    def test_luck_factor_calculation(self):
        from fixtures_collector import transform_l5_stats
        df = pd.DataFrame({
            'fixture_id': [1],
            'date': ['2025-01-01'],
            'league_id': [39], 'league_name': ['PL'],
            'home_id': [10], 'home_name': ['A'],
            'away_id': [20], 'away_name': ['B'],
            'goals_home': [3], 'goals_away': [0],
            'xg_home': [1.0], 'xg_away': [0.5],
            'winner_id': [10],
            'round_number': [1],
        })
        result = transform_l5_stats(df)
        team_10 = result[result['team_id'] == 10].iloc[0]
        # luck = avg_scored - avg_xg_for = 3 - 1 = 2.0
        assert team_10['luck_factor'] == 2.0


class TestTransformLeagueStats:
    def test_returns_dataframe(self, sample_fixtures_df):
        from fixtures_collector import transform_league_stats
        result = transform_league_stats(sample_fixtures_df)
        assert isinstance(result, pd.DataFrame)

    def test_correct_number_of_leagues(self, sample_fixtures_df):
        from fixtures_collector import transform_league_stats
        result = transform_league_stats(sample_fixtures_df)
        # sample_fixtures_df ma PL (id=39) i BL (id=78)
        assert len(result) == 2

    def test_required_columns(self, sample_fixtures_df):
        from fixtures_collector import transform_league_stats
        result = transform_league_stats(sample_fixtures_df)
        required = {'league_id', 'league_name', 'l_avg_scored_home',
                    'l_avg_scored_away', 'l_avg_xg_home', 'l_avg_xg_away'}
        assert required.issubset(set(result.columns))

    def test_averages_correct(self):
        from fixtures_collector import transform_league_stats
        df = pd.DataFrame({
            'league_id': [39, 39],
            'league_name': ['PL', 'PL'],
            'goals_home': [2.0, 4.0],
            'goals_away': [1.0, 3.0],
            'xg_home': [1.5, 2.5],
            'xg_away': [0.8, 1.2],
        })
        result = transform_league_stats(df)
        row = result.iloc[0]
        assert row['l_avg_scored_home'] == pytest.approx(3.0, abs=0.01)
        assert row['l_avg_scored_away'] == pytest.approx(2.0, abs=0.01)

    def test_no_database_call(self, sample_fixtures_df, monkeypatch):
        """Transformacja nie powinna dotykać bazy danych."""
        from fixtures_collector import transform_league_stats
        import fixtures_collector as fc
        called = []
        monkeypatch.setattr(fc, 'engine', type('E', (), {'connect': lambda *a: called.append(1)})())
        transform_league_stats(sample_fixtures_df)
        assert len(called) == 0

    def test_empty_df_returns_empty(self):
        from fixtures_collector import transform_league_stats
        result = transform_league_stats(pd.DataFrame())
        assert result.empty


# ===========================================================================
# TESTY: result_checker.py
# ===========================================================================

class TestEvaluateMarket:
    @pytest.mark.parametrize("market,gh,ga,expected", [
        ('1',          2, 1, True),
        ('1',          1, 2, False),
        ('1',          1, 1, False),
        ('X',          1, 1, True),
        ('X',          2, 1, False),
        ('2',          1, 2, True),
        ('2',          2, 1, False),
        ('Over 2.5',   2, 1, True),
        ('Over 2.5',   1, 1, False),
        ('Over 2.5',   0, 0, False),
        ('Under 2.5',  1, 1, True),
        ('Under 2.5',  2, 1, False),
        ('BTTS Yes',   1, 1, True),
        ('BTTS Yes',   0, 1, False),
        ('BTTS Yes',   1, 0, False),
        ('BTTS No',    0, 1, True),
        ('BTTS No',    1, 0, True),
        ('BTTS No',    1, 1, False),
        ('Unknown',    1, 1, None),
    ])
    def test_evaluate_market(self, market, gh, ga, expected):
        from result_checker import evaluate_market
        assert evaluate_market(market, gh, ga) == expected


class TestTransformBetResults:
    def test_empty_finished_matches_returns_empty(self):
        from result_checker import transform_bet_results
        result = transform_bet_results(pd.DataFrame(), {}, set())
        assert result.empty

    def test_empty_vb_df_returns_empty(self):
        from result_checker import transform_bet_results
        result = transform_bet_results(pd.DataFrame(), {1: (2, 1)}, set())
        assert result.empty

    def test_won_bet_recorded(self):
        from result_checker import transform_bet_results
        vb_df = pd.DataFrame([{
            'fixture_id': 1, 'market': '1',
            'date': '2025-01-01', 'league_name': 'PL',
            'home_name': 'A', 'away_name': 'B',
            'fair_odd': 2.0, 'bookie_odd': 2.2, 'edge': 0.1,
            'hints': '', 'bet_result': 'pending',
        }])
        finished = {1: (2, 1)}  # A wygrała → rynek '1' wygrany
        result = transform_bet_results(vb_df, finished, set())
        assert len(result) == 1
        assert result.iloc[0]['bet_result'] == 'won'

    def test_lost_bet_recorded(self):
        from result_checker import transform_bet_results
        vb_df = pd.DataFrame([{
            'fixture_id': 1, 'market': '1',
            'date': '2025-01-01', 'league_name': 'PL',
            'home_name': 'A', 'away_name': 'B',
            'fair_odd': 2.0, 'bookie_odd': 2.2, 'edge': 0.1,
            'hints': '', 'bet_result': 'pending',
        }])
        finished = {1: (0, 2)}  # B wygrała → rynek '1' przegrany
        result = transform_bet_results(vb_df, finished, set())
        assert result.iloc[0]['bet_result'] == 'lost'

    def test_deduplication_removes_existing(self):
        from result_checker import transform_bet_results
        vb_df = pd.DataFrame([{
            'fixture_id': 1, 'market': '1',
            'date': '2025-01-01', 'league_name': 'PL',
            'home_name': 'A', 'away_name': 'B',
            'fair_odd': 2.0, 'bookie_odd': 2.2, 'edge': 0.1,
            'hints': '', 'bet_result': 'pending',
        }])
        finished = {1: (2, 1)}
        existing_keys = {(1, '1')}  # już zapisane
        result = transform_bet_results(vb_df, finished, existing_keys)
        assert result.empty  # zduplikowany zakład pominięty

    def test_unknown_market_skipped(self):
        from result_checker import transform_bet_results
        vb_df = pd.DataFrame([{
            'fixture_id': 1, 'market': 'UNKNOWN_MARKET',
            'date': '2025-01-01', 'league_name': 'PL',
            'home_name': 'A', 'away_name': 'B',
            'fair_odd': 2.0, 'bookie_odd': 2.2, 'edge': 0.1,
            'hints': '', 'bet_result': 'pending',
        }])
        finished = {1: (2, 1)}
        result = transform_bet_results(vb_df, finished, set())
        assert result.empty

    def test_no_database_call(self, monkeypatch):
        """transform_bet_results jest czystą funkcją – bez I/O."""
        from result_checker import transform_bet_results
        import result_checker as rc
        called = []
        monkeypatch.setattr(rc, 'engine', type('E', (), {'connect': lambda *a: called.append(1)})())
        vb_df = pd.DataFrame([{
            'fixture_id': 1, 'market': '1',
            'date': '2025-01-01', 'league_name': 'PL',
            'home_name': 'A', 'away_name': 'B',
            'fair_odd': 2.0, 'bookie_odd': 2.2, 'edge': 0.1,
            'hints': '', 'bet_result': 'pending',
        }])
        transform_bet_results(vb_df, {1: (2, 1)}, set())
        assert len(called) == 0


# ===========================================================================
# TESTY: bet_engine.py
# ===========================================================================

class TestDcTau:
    def test_00_correction(self):
        from bet_engine import _dc_tau, RHO
        lh, la = 1.5, 1.2
        expected = 1 - lh * la * RHO
        assert _dc_tau(0, 0, lh, la) == pytest.approx(expected)

    def test_10_correction(self):
        from bet_engine import _dc_tau, RHO
        lh, la = 1.5, 1.2
        assert _dc_tau(1, 0, lh, la) == pytest.approx(1 + la * RHO)

    def test_01_correction(self):
        from bet_engine import _dc_tau, RHO
        lh, la = 1.5, 1.2
        assert _dc_tau(0, 1, lh, la) == pytest.approx(1 + lh * RHO)

    def test_11_correction(self):
        from bet_engine import _dc_tau, RHO
        assert _dc_tau(1, 1, 1.5, 1.2) == pytest.approx(1 - RHO)

    def test_high_score_no_correction(self):
        from bet_engine import _dc_tau
        assert _dc_tau(5, 5, 1.5, 1.2) == 1.0
        assert _dc_tau(3, 2, 1.0, 1.0) == 1.0


class TestBuildMatrix:
    def test_sums_to_one(self):
        from bet_engine import _build_matrix
        m = _build_matrix(1.5, 1.2)
        assert abs(m.sum() - 1.0) < 1e-6

    def test_shape_10x10(self):
        from bet_engine import _build_matrix
        m = _build_matrix(1.5, 1.2)
        assert m.shape == (10, 10)

    def test_all_non_negative(self):
        from bet_engine import _build_matrix
        m = _build_matrix(1.5, 1.2)
        assert (m >= 0).all()

    def test_zero_lambda_handled(self):
        from bet_engine import _build_matrix
        m = _build_matrix(0, 0)  # min clamp do 0.01
        assert abs(m.sum() - 1.0) < 1e-6


class TestFindValueBets:
    def _make_output_df(self):
        return pd.DataFrame([{
            'league_id': 39, 'league_name': 'PL', 'fixture_id': 1,
            'date': '2025-01-01', 'home_name': 'A', 'away_name': 'B',
            'home_id': 10, 'away_id': 20,
            'fair_home': 2.0, 'fair_draw': 3.5, 'fair_away': 4.0,
            'fair_over25': 1.9, 'fair_under25': 2.1,
            'fair_btts_yes': 1.8, 'fair_btts_no': 2.2,
            'odd_home': 2.5,    # edge = 2.5/2.0 - 1 = 0.25 → value bet
            'odd_draw': 3.4,    # edge = 3.4/3.5 - 1 < 0 → nie value
            'odd_away': 4.5,    # edge = 4.5/4.0 - 1 = 0.125 → value bet
            'odd_over_25': 1.7, # edge = 1.7/1.9 - 1 < 0 → nie value
            'odd_under_25': 2.0,
            'odd_btts_yes': 1.7,
            'odd_btts_no': 2.1,
            'hints': '',
        }])

    def test_detects_value_bets(self):
        from bet_engine import find_value_bets
        df = self._make_output_df()
        result = find_value_bets(df, min_edge=0.05)
        assert len(result) > 0

    def test_correct_markets_flagged(self):
        from bet_engine import find_value_bets
        df = self._make_output_df()
        result = find_value_bets(df, min_edge=0.05)
        markets = set(result['market'].tolist())
        assert '1' in markets   # odd_home=2.5 > fair=2.0 → value
        assert '2' in markets   # odd_away=4.5 > fair=4.0 → value
        assert 'X' not in markets  # odd_draw=3.4 < fair=3.5 → brak value

    def test_high_threshold_returns_empty(self):
        from bet_engine import find_value_bets
        df = self._make_output_df()
        result = find_value_bets(df, min_edge=0.99)
        assert result.empty

    def test_sorted_by_edge_descending(self):
        from bet_engine import find_value_bets
        df = self._make_output_df()
        result = find_value_bets(df, min_edge=0.05)
        if len(result) > 1:
            edges = result['edge'].tolist()
            assert edges == sorted(edges, reverse=True)

    def test_bet_result_is_pending(self):
        from bet_engine import find_value_bets
        df = self._make_output_df()
        result = find_value_bets(df, min_edge=0.05)
        assert (result['bet_result'] == 'pending').all()

    def test_no_database_call(self, monkeypatch):
        from bet_engine import find_value_bets
        import bet_engine as be
        called = []
        monkeypatch.setattr(be, 'engine', type('E', (), {'connect': lambda *a: called.append(1)})())
        find_value_bets(self._make_output_df(), min_edge=0.05)
        assert len(called) == 0
