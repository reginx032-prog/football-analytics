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

# Statusy API-Football oznaczające zakończony mecz
FINISHED_STATUSES = {'FT', 'AET', 'PEN', 'AWD', 'WO'}

RATE_LIMIT_DELAY = 0.2  # sekundy między requestami


def check_and_update_finished():
    """
    1. Pobiera z tabeli 'upcoming_odds' wszystkie mecze z is_finished='no'.
    2. Dla każdego fixture_id odpytuje API-Football /fixtures?id=...
    3. Jeśli status meczu należy do FINISHED_STATUSES → UPDATE is_finished='yes'.
    """
    # 1. Pobieramy fixture_id do sprawdzenia
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

    finished_ids = []

    # 2. Sprawdzamy status każdego meczu w API
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
                status = data[0].get('fixture', {}).get('status', {}).get('short', '')
                if status in FINISHED_STATUSES:
                    finished_ids.append(int(f_id))
                    logger.info(f"✔ Mecz {f_id} zakończony (status: {status})")
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

    # 3. Aktualizujemy bazę danych
    if not finished_ids:
        logger.info("Brak nowych zakończonych meczów do zaktualizowania.")
        return

    try:
        with engine.connect() as conn:
            for f_id in finished_ids:
                conn.execute(
                    text("UPDATE upcoming_odds SET is_finished = 'yes' WHERE fixture_id = :fid"),
                    {'fid': f_id}
                )
            conn.commit()
        logger.info(f"Zaktualizowano {len(finished_ids)} meczów → is_finished='yes'.")
    except Exception as e:
        logger.error(f"Błąd podczas aktualizacji bazy: {e}", exc_info=True)


if __name__ == "__main__":
    check_and_update_finished()
