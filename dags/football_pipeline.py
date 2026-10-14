
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'football-analytics',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'email_on_failure': False,
}


# =============================================================================
# DAG 1: Pre-match pipeline — piątek 09:00 UTC
# =============================================================================

with DAG(
    dag_id='football_pre_match_pipeline',
    default_args=default_args,
    description='Weekly: collect stats & generate value bets',
    schedule='0 9 * * 1',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['football', 'pre-match'],
) as pre_match_dag:

    def _run_teams():
        from main import main
        main()

    def _run_standings():
        from standings_collector import run_standings_collection
        run_standings_collection()

    def _run_fixtures():
        from fixtures_collector import run_collection
        run_collection()

    def _run_upcoming_odds():
        from upcoming_odds import run_odds_collection
        run_odds_collection()

    def _run_bet_engine():
        from bet_engine import main
        main()

    t_teams     = PythonOperator(task_id='collect_teams',         python_callable=_run_teams)
    t_standings = PythonOperator(task_id='collect_standings',     python_callable=_run_standings)
    t_fixtures  = PythonOperator(task_id='collect_fixtures',      python_callable=_run_fixtures)
    t_odds      = PythonOperator(task_id='collect_upcoming_odds', python_callable=_run_upcoming_odds)
    t_bets      = PythonOperator(task_id='run_bet_engine',        python_callable=_run_bet_engine)

    t_teams >> t_standings >> t_fixtures >> t_odds >> t_bets


# =============================================================================
# DAG 2: Result checker — codziennie 23:00 UTC
# =============================================================================

with DAG(
    dag_id='football_result_checker',
    default_args=default_args,
    description='Daily: check finished matches & update historical_bets',
    schedule='0 23 * * *',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['football', 'results'],
) as result_dag:

    def _run_result_checker():
        from result_checker import check_and_update_finished
        check_and_update_finished()

    PythonOperator(
        task_id='check_results',
        python_callable=_run_result_checker,
    )
