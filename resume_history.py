"""
resume_history.py — wznawia pobieranie fixtures_history OD wskazanej ligi.

Pierwotny run_collection() w fixtures_history.py leci od początku TOP_20_LEAGUES
i dopisuje (append), więc po przerwaniu nie da się go wznowić bez duplikatów.
Ten skrypt pobiera ligi od START_LEAGUE_ID do końca listy TOP_20_LEAGUES dla danego
sezonu, zapisuje KAŻDĄ ligę osobno (postęp przeżywa przerwanie / dzienny limit API)
i POMIJA ligi już obecne w bazie dla tego sezonu — można go odpalać wielokrotnie.

Użycie:
    python resume_history.py                # od Arabii (307), sezon 2025
    python resume_history.py 40             # od Championship (40), sezon 2025
    python resume_history.py 40 2024        # od Championship, sezon 2024
"""
import sys
import time

import pandas as pd
from sqlalchemy import text

from config import engine, logger, TOP_20_LEAGUES
from fixtures_history import fetch_fixtures, RateLimitError

START_LEAGUE_ID    = int(sys.argv[1]) if len(sys.argv) > 1 else 307   # Saudi Pro League
SEASON             = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
INTER_LEAGUE_DELAY = 1.2


def _existing_count(league_id: int, season: int) -> int:
    with engine.connect() as conn:
        return int(pd.read_sql(
            text("SELECT COUNT(*) n FROM fixtures_history WHERE season=:s AND league_id=:l"),
            conn, params={"s": season, "l": league_id})["n"].iloc[0])


def _save_league(df: pd.DataFrame) -> None:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_sql("fixtures_history", engine, if_exists="append", index=False)


def main():
    ids = list(TOP_20_LEAGUES.keys())
    if START_LEAGUE_ID not in ids:
        logger.error(f"START_LEAGUE_ID={START_LEAGUE_ID} nie ma w TOP_20_LEAGUES.")
        return
    todo = ids[ids.index(START_LEAGUE_ID):]
    logger.info(f"Wznawiam sezon {SEASON} od ligi {START_LEAGUE_ID}. "
                f"Do zrobienia: {[TOP_20_LEAGUES[l] for l in todo]}")

    saved_total, done = 0, []
    for lid in todo:
        name = TOP_20_LEAGUES[lid]

        existing = _existing_count(lid, SEASON)
        if existing:
            logger.warning(f"  {name}: już {existing} wierszy w bazie (sezon {SEASON}) — pomijam.")
            continue

        try:
            df = fetch_fixtures(lid, name, SEASON)
        except RateLimitError as e:
            logger.error(f"DZIENNY LIMIT API przy {name}: {e}")
            logger.warning(f"Zatrzymuję się. Wznów jutro: 'python resume_history.py {lid} {SEASON}' "
                           f"(albo bez argumentów — pominie już pobrane ligi).")
            break

        if df is not None and not df.empty:
            _save_league(df)
            saved_total += len(df)
            done.append(name)
            logger.info(f"  ZAPISANO {name}: {len(df)} meczów (łącznie w tej sesji: {saved_total}).")
        else:
            logger.warning(f"  {name}: brak meczów (nic nie zapisano).")

        time.sleep(INTER_LEAGUE_DELAY)

    logger.info(f"Koniec sesji. Pobrane ligi: {done or '(żadnej)'}. Łącznie {saved_total} meczów.")


if __name__ == "__main__":
    main()
