import requests
import pandas as pd
import time
import logging
from sqlalchemy import text

# --- KONFIGURACJA ---
try:
    from main import BASE_URL, HEADERS, logger, engine
except ImportError:
    print("❌ Błąd: Nie znaleziono pliku main.py lub brak w nim potrzebnych stałych.")
    exit()

FINISHED_STATUSES = {'FT', 'AET', 'PEN', 'AWD', 'WO'}
RATE_LIMIT_DELAY = 0.2


def evaluate_market(market, goals_home, goals_away):
    """Zwraca True (wygrany), False (przegrany) lub None (nieznany rynek)."""
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


def save_to_historical(finished_matches):
    """
    Czyta value_bets dla zakończonych meczów, ocenia każdy rynek
    i zapisuje wyniki do tabeli historical_bets (append + deduplicacja).
    finished_matches: dict {fixture_id: (goals_home, goals_away)}
    """
    if not finished_matches:
        return

    fixture_ids = list(finished_matches.keys())

    try:
        vb_df = pd.read_sql(
            text("SELECT * FROM value_bets WHERE fixture_id IN :ids"),
            engine,
            params={'ids': tuple(fixture_ids)}
        )
    except Exception as e:
        logger.error(f"Błąd odczytu value_bets: {e}", exc_info=True)
        return

    if vb_df.empty:
        logger.info("Brak value betów dla zakończonych meczów.")
        return

    rows = []
    for _, row in vb_df.iterrows():
        f_id = int(row['fixture_id'])
        market = row['market']
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
        logger.info("Brak zakładów do zapisania w historii.")
        return

    hist_df = pd.DataFrame(rows)

    # Deduplicacja — nie zapisuj ponownie tych samych fixture_id + market
    try:
        existing = pd.read_sql(
            text("SELECT fixture_id, market FROM historical_bets"),
            engine
        )
        if not existing.empty:
            existing_keys = set(zip(existing['fixture_id'].astype(int), existing['market']))
            hist_df = hist_df[~hist_df.apply(
                lambda r: (int(r['fixture_id']), r['market']) in existing_keys, axis=1
            )]
    except Exception:
        pass  # Tabela jeszcze nie istnieje — pierwsze uruchomienie

    if hist_df.empty:
        logger.info("Wszystkie zakłady już są w historii (duplikaty pominięte).")
        return

    try:
        hist_df.to_sql('historical_bets', engine, if_exists='append', index=False)
        won  = (hist_df['bet_result'] == 'won').sum()
        lost = (hist_df['bet_result'] == 'lost').sum()
        logger.info(f"Zapisano {len(hist_df)} zakładów do historical_bets ({won} won, {lost} lost).")
    except Exception as e:
        logger.error(f"Błąd zapisu do historical_bets: {e}", exc_info=True)


def check_and_update_finished():
    """
    1. Pobiera z 'upcoming_odds' mecze z is_finished='no'.
    2. Odpytuje API-Football dla każdego fixture_id.
    3. Zakończone mecze → UPDATE is_finished='yes' w upcoming_odds.
    4. Zakończone mecze → ocena zakładów i zapis do historical_bets.
    """
    try:
        df = pd.read_sql(
            "SELECT fixture_id FROM upcoming_odds WHERE is_finished = 'no'",
            engine
        )
    except Exception as e:
        logger.error(f"Błąd odczytu upcoming_odds: {e}", exc_info=True)
        return

    if df.empty:
        logger.info("Brak meczów do sprawdzenia (wszystkie mają is_finished='yes').")
        return

    fixture_ids = df['fixture_id'].tolist()
    logger.info(f"Sprawdzam {len(fixture_ids)} meczów...")

    finished_matches = {}  # {fixture_id: (goals_home, goals_away)}

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
                        finished_matches[int(f_id)] = (int(gh), int(ga))
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

    if not finished_matches:
        logger.info("Brak nowych zakończonych meczów.")
        return

    finished_ids = list(finished_matches.keys())

    # UPDATE upcoming_odds
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE upcoming_odds SET is_finished = 'yes' WHERE fixture_id IN :ids"),
                {'ids': tuple(finished_ids)}
            )
            conn.commit()
        logger.info(f"Zaktualizowano {len(finished_ids)} meczów → is_finished='yes'.")
    except Exception as e:
        logger.error(f"Błąd podczas aktualizacji bazy: {e}", exc_info=True)
        return

    # Zapis do historical_bets
    save_to_historical(finished_matches)


if __name__ == "__main__":
    check_and_update_finished()
