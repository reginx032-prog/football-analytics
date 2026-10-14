# Football Analytics

System do analizy meczów piłkarskich i wykrywania value betów oparty na statystykach (forma, xG, tabela).

## Architektura

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Compose                      │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │  React   │───▶│  Spring  │───▶│   PostgreSQL     │   │
│  │ Frontend │    │   Boot   │    │  (football_data) │   │
│  │  :80     │    │  :8081   │    │     :5433        │   │
│  └──────────┘    └──────────┘    └──────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  Apache Airflow                 │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │ Pre-match pipeline (poniedz. 09:00 UTC) │    │    │
│  │  │ Teams → Standings → Fixtures → Odds     │    │    │
│  │  │ → Bet Engine                            │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │ Result checker (codziennie 23:00 UTC)   │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  │  Webserver :8082 │ DB (airflow) :5434           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Frontend | React 18, Vite, nginx |
| Backend | Java 21, Spring Boot 4, Hibernate |
| ETL / Pipeline | Python 3.12, pandas, NumPy, SciPy |
| Model ML | XGBoost, scikit-learn, pytest |
| Scheduler | Apache Airflow 2.11.2 |
| Baza danych | PostgreSQL 15 |
| Infrastruktura | Docker Compose |

## Funkcjonalności

- **Tabele ligowe** — aktualne standings z top lig
- **Nadchodzące mecze** — kursy bukmacherskie na mecze tygodnia
- **Value Bets** — wykryte zakłady z dodatnim edge względem fair odds
- **Historical Bets** — historia zakładów z wynikami i yield
- **Historia meczów** — wyniki i xG z poprzednich sezonów (`fixtures_history`) jako baza pod model ML
- **Featury pod XGBoost** — rolling statystyki drużyn i kontekst ligi liczone bez wycieku danych (`xgb_features`)
- **Model XGBoost** — przewiduje liczbę goli i z niej prawdopodobieństwa rynków 1X2, Over/Under 2.5 i BTTS

## Jak uruchomić

### Wymagania
- Docker + Docker Compose

### Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij klucz API:

```env
API_KEY=twoj_klucz_api_football
```

Klucz API uzyskasz na [api-sports.io](https://api-sports.io).

### Uruchomienie

```bash
mkdir -p logs plugins
docker compose up -d --build
```

### Dostęp

| Serwis | URL | Login |
|--------|-----|-------|
| Frontend | http://localhost | — |
| Airflow | http://localhost:8082 | admin / admin |
| pgAdmin | http://localhost:8080 | admin@admin.com / admin |
| Backend API | http://localhost:8081 | — |

## Struktura projektu

```
football-analytics/
├── dags/
│   └── football_pipeline.py    # Definicje DAGów Airflow
├── backend/                    # Spring Boot API
│   └── src/
├── frontend/                   # React aplikacja
│   └── src/
├── main.py                     # Kolektor danych o drużynach
├── standings_collector.py      # Kolektor tabeli ligowej
├── fixtures_collector.py       # Kolektor nadchodzących meczów
├── upcoming_odds.py            # Kolektor kursów bukmacherskich
├── bet_engine.py               # Silnik wykrywania value betów
├── result_checker.py           # Weryfikator wyników zakładów
├── fixtures_history.py         # Kolektor historii meczów (wyniki, xG, kursy)
├── resume_history.py           # Wznawianie pobierania historii od wybranej ligi
├── xgb_model.py                # Feature engineering pod model XGBoost
├── xgb_train.py                # Trening i ewaluacja modelu XGBoost
├── tests/
│   └── test_xgb.py             # Testy featurów i ewaluacji (pytest)
├── scripts/
│   └── restore-db.ps1          # Przywracanie bazy z football_data.dump
├── models/                     # Artefakty treningu (generowane, poza gitem)
├── config.py                   # Konfiguracja API, ligi, połączenie z DB
├── docker-compose.yaml
└── requirements.txt
```

## Pipeline

```
Poniedziałek 09:00 UTC (football_pre_match_pipeline)
────────────────────────────────────────────────────
collect_teams
    └─▶ collect_standings
            └─▶ collect_fixtures
                    └─▶ collect_upcoming_odds
                                └─▶ run_bet_engine

Codziennie 23:00 UTC (football_result_checker)
────────────────────────────────────────────────────
check_results  (aktualizuje historical_bets)
```

## Logika value betów

Bet Engine porównuje kursy bukmacherskie z kursami fair obliczonymi na podstawie statystyk drużyn (forma, xG, tabela). Zakład jest oznaczany jako value bet gdy:

```
edge = (1 / fair_odd) - (1 / bookmaker_odd) > próg
```

## Model XGBoost (ręcznie, poza Airflow)

```bash
python fixtures_history.py   # pobiera historię meczów do tabeli fixtures_history
python resume_history.py 40  # (opcjonalnie) wznawia pobieranie od ligi 40 po przerwaniu / limicie API
python xgb_model.py          # buduje featury i zapisuje je do tabeli xgb_features
python xgb_train.py          # trenuje i ewaluuje model, artefakty zapisuje w models/
```

`fixtures_history.py` rozróżnia dzienny limit API (przerwanie) od limitu na minutę i błędów 503 (odczekanie i ponowienie).

### Featury — `xgb_model.py`

Bierze 12 lig z dobrym pokryciem xG, uzupełnia brakujące xG golami i dla każdego meczu tworzy 2 wiersze (perspektywa gospodarza i gościa) z:

- formą drużyny i rywala z ostatnich 5 i 10 meczów (xG, gole, W/D/L, BTTS),
- kontekstem ligi — średnie gole i xG gospodarzy / gości z meczów zakończonych przed startem spotkania,
- liczbą rozegranych meczów (wiersz powstaje dopiero, gdy obie drużyny mają ≥ 10 meczów w sezonie).

Featury liczone są per sezon, wyłącznie z meczów rozegranych **przed** danym spotkaniem — historia obu drużyn aktualizowana jest dopiero po zbudowaniu wierszy.

### Trening i ewaluacja — `xgb_train.py`

- **Model:** XGBoost z regresją Poissona (`count:poisson`) przewiduje oczekiwaną liczbę goli (λ) każdej drużyny.
- **Rynki:** λ gospodarza i gościa → macierz wyników z korektą Dixon-Colesa (ρ) → prawdopodobieństwa 1X2, Over/Under 2.5, BTTS.
- **Podział po dacie:** trening < 2025-01-01 ≤ walidacja < 2025-07-01 ≤ test. Walidacja służy do early stoppingu, doboru alpha GLM i wagi mieszanki. Test oceniany jest raz, na końcu.
- **ρ Dixon-Colesa** estymowane z λ out-of-fold na treningu (GroupKFold po meczu) i z walidacji, bez danych testowych.
- **Porównywane modele:** `xgboost`, `glm` (liniowa regresja Poissona, punkt odniesienia), `blend` (średnia geometryczna λ), `old_formula` (wzór z `bet_engine.py`), `league_avg`.
- **Metryki:** dewiancja Poissona, logloss / RPS / Brier dla 1X2, logloss / Brier dla O/U 2.5 i BTTS, NLL dokładnego wyniku, porównanie parami z wartością z, kalibracja (ogólna, łączny test χ² dla 1X2, decyle) i ważność cech.

Artefakty w `models/`: `xgb_goals.json`, `glm_goals.joblib`, `xgb_goals_meta.json` (parametry i metryki), `test_predictions.csv`.

### Testy

```bash
pytest tests/
```

Testy na syntetycznych danych sprawdzają m.in. brak wycieku wyniku meczu do jego featurów, kontekst ligi przy meczach przechodzących przez północ UTC, macierz Dixon-Colesa, prawdopodobieństwa rynków, estymację ρ i rozłączność podziału czasowego.

## Przywracanie bazy z dumpu

```powershell
.\scripts\restore-db.ps1                 # przywraca football_data.dump do kontenera football_db_container
.\scripts\restore-db.ps1 -SkipBackup     # bez kopii zapasowej obecnej bazy
```

Domyślnie przed przywróceniem tworzy kopię obecnej bazy (`pg_dump`) obok pliku dumpu i prosi o potwierdzenie (`YES`). `-Force` pomija pytanie. Istniejące tabele są zastępowane (`pg_restore --clean`).
