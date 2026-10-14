import requests
import pandas as pd
import time
import logging
from sqlalchemy import text

from config import BASE_URL, HEADERS, logger, engine

FINISHED_STATUSES = {'FT', 'AET', 'PEN', 'AWD', 'WO'}
RATE_LIMIT_DELAY = 0.2


# =============================================================================
# TRANSFORM (czysta funkcja, bez I/O)
# =============================================================================

def evaluate_market(market, goals_home, goals_away):
    """TRANSFORM: Zwraca True (wygrany), False (przegrany) lub None (nieznany rynek)."""
    total = goals_home + goals_away
    if market == '1':
        return goals_home > goals_away
    elif market == 'X':
        return goals_home == goals_away
    elif market == '2':
        return goals_away > goals_home
    elif market == 'Over 2.5':
        return total >= 3
    elif market == 'Under 2.5':
        return total <= 2
    elif market == 'BTTS Yes':
        return goals_home >= 1 and goals_away >= 1
    elif market == 'BTTS No':
        return goals_home == 0 or goals_away == 0
    return None


def transform_bet_results(vb_df, finished_matches, existing_keys):
    """
    TRANSFORM: Ocenia wyniki zakładów, deduplikuje względem istniejących rekordów.
    Przyjmuje gotowe dane (bez I/O). Zwraca DataFrame gotowy do zapisu.

    vb_df:            DataFrame z value_bets dla zakończonych meczów
    finished_matches: dict {fixture_id: (goals_home, goals_away)}
    existing_keys:    set par (fixture_id, market) już zapisanych w historical_bets
    """
    if vb_df.empty or not finished_matches:
        return pd.DataFrame()

    rows = []
    for _, row in vb_df.iterrows():
        f_id = int(row['fixture_id'])
        market = row['market']

        if f_id not in finished_matches:
            continue

        goals_home, goals_away = finished_matches[f_id]
        result = evaluate_market(market, goals_home, goals_away)

        if result is None:
            continue

        rows.append({
            'fixture_id':  f_id,
            'market':      market,
            'date':        row['date'],
            'league_name': row['league_name'],
            'home_name':   row['home_name'],
            'away_name':   row['away_name'],
            'fair_odd':    row['fair_odd'],
            'bookie_odd':  row['bookie_odd'],
            'edge':        row['edge'],
            'hints':       row.get('hints', ''),
            'bet_result':  'won' if result else 'lost',
            'goals_home':  goals_home,
            'goals_away':  goals_away,
        })

    if not rows:
        return pd.DataFrame()

    hist_df = pd.DataFrame(rows)

    if existing_keys:
        hist_df = hist_df[~hist_df.apply(
            lambda r: (int(r['fixture_id']), r['market']) in existing_keys, axis=1
        )]

    return hist_df


# =============================================================================
# EXTRACT
# =============================================================================

def extract_pending_fixture_ids():
    """EXTRACT: Pobiera ID niezakończonych meczów z tabeli upcoming_odds."""
    try:
        df = pd.read_sql(
            "SELECT fixture_id FROM upcoming_odds WHERE is_finished = 'no'",
            engine
        )
        return df['fixture_id'].tolist()
    except Exception as e:
        logger.error(f"Błąd odczytu upcoming_odds: {e}", exc_info=True)
        return []


def extract_finished_results(fixture_ids):
    """
    EXTRACT: Odpytuje API-Football dla każdego fixture_id.
    Zwraca dict {fixture_id: (goals_home, goals_away)} tylko dla zakończonych meczów.
    """
    finished = {}
    logger.info(f"Sprawdzam {len(fixture_ids)} meczów...")

    for f_id in fixture_ids:
        try:
            response = requests.get(
                f"{BASE_URL}/fixtures",
                headers=HEADERS,
                params={'id': f_id},
                timeout=10
            )
            response.raise_for_status()
            data = response.json().get('response', [])

            if data:
                fixture_data = data[0]
                status = fixture_data.get('fixture', {}).get('status', {}).get('short', '')
                if status in FINISHED_STATUSES:
                    gh = fixture_data.get('goals', {}).get('home')
                    ga = fixture_data.get('goals', {}).get('away')
                    if gh is not None and ga is not None:
                        finished[int(f_id)] = (int(gh), int(ga))
                        logger.info(f"✔ Mecz {f_id} zakończony ({gh}:{ga}, status: {status})")
                    else:
                        logger.warning(f"Mecz {f_id} zakończony ale brak danych o golach")
                else:
                    logger.info(f"○ Mecz {f_id} jeszcze nie zakończony (status: {status})")
            else:
                logger.warning(f"Brak danych API dla fixture {f_id}")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout dla fixture {f_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd HTTP dla fixture {f_id}: {e}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd dla fixture {f_id}: {e}", exc_info=True)

        time.sleep(RATE_LIMIT_DELAY)

    return finished


def extract_value_bets(fixture_ids):
    """EXTRACT: Pobiera zakłady z tabeli value_bets dla podanych fixture_ids."""
    try:
        vb_df = pd.read_sql(
            text("SELECT * FROM value_bets WHERE fixture_id IN :ids"),
            engine,
            params={'ids': tuple(fixture_ids)}
        )
        return vb_df
    except Exception as e:
        logger.error(f"Błąd odczytu value_bets: {e}", exc_info=True)
        return pd.DataFrame()


def extract_existing_historical_keys():
    """EXTRACT: Pobiera istniejące pary (fixture_id, market) z historical_bets do deduplicacji."""
    try:
        existing = pd.read_sql(
            text("SELECT fixture_id, market FROM historical_bets"),
            engine
        )
        if not existing.empty:
            return set(zip(existing['fixture_id'].astype(int), existing['market']))
        return set()
    except Exception:
        return set()


# =============================================================================
# LOAD
# =============================================================================

def load_results(finished_ids, hist_df):
    """
    LOAD: Aktualizuje is_finished i zapisuje historical_bets w jednej transakcji.
    Używamy engine.begin(), aby zapewnić automatyczny COMMIT na końcu bloku
    lub ROLLBACK w przypadku jakiegokolwiek błędu.
    """
    try:
        # engine.begin() otwiera połączenie i transakcję jednocześnie
        with engine.begin() as conn:
            # 1. Aktualizacja statusu meczów
            conn.execute(
                text("UPDATE upcoming_odds SET is_finished = 'yes' WHERE fixture_id IN :ids"),
                {'ids': tuple(finished_ids)}
            )
            logger.info(f"Zaktualizowano {len(finished_ids)} meczów w upcoming_odds.")

            # 2. Zapis zakładów przez Pandas
            if not hist_df.empty:
                # KLUCZOWE: W SQLAlchemy 2.0 przekazujemy 'conn' do to_sql.
                # Pandas wykryje, że transakcja jest już otwarta i NIE wywoła conn.commit()
                hist_df.to_sql(
                    name='historical_bets',
                    con=conn,
                    if_exists='append',
                    index=False
                )

                won = (hist_df['bet_result'] == 'won').sum()
                lost = (hist_df['bet_result'] == 'lost').sum()
                logger.info(f"Zapisano {len(hist_df)} rekordów do historical_bets ({won} won, {lost} lost).")

        # Tutaj transakcja jest już automatycznie zatwierdzona (po wyjściu z bloku with)
        logger.info("Transakcja zakończona pomyślnie (Atomic Load OK).")

    except Exception as e:
        # Jeśli cokolwiek pójdzie nie tak wewnątrz 'with',
        # SQLAlchemy automatycznie wywoła ROLLBACK.
        logger.error(f"Błąd transakcji – dane nie zostały zapisane: {e}", exc_info=True)
        raise


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def check_and_update_finished():
    """
    Sprawdza zakończone mecze i aktualizuje historię zakładów (E → T → L).
    """
    # --- EXTRACT ---
    fixture_ids = extract_pending_fixture_ids()
    if not fixture_ids:
        logger.info("Brak meczów do sprawdzenia (wszystkie mają is_finished='yes').")
        return

    finished_matches = extract_finished_results(fixture_ids)
    if not finished_matches:
        logger.info("Brak nowych zakończonych meczów.")
        return

    finished_ids = list(finished_matches.keys())
    vb_df = extract_value_bets(finished_ids)
    existing_keys = extract_existing_historical_keys()

    # --- TRANSFORM ---
    hist_df = transform_bet_results(vb_df, finished_matches, existing_keys)

    # --- LOAD ---
    load_results(finished_ids, hist_df)


if __name__ == "__main__":
    check_and_update_finished()