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
| Scheduler | Apache Airflow 2.11.2 |
| Baza danych | PostgreSQL 15 |
| Infrastruktura | Docker Compose |

## Funkcjonalności

- **Tabele ligowe** — aktualne standings z top lig
- **Nadchodzące mecze** — kursy bukmacherskie na mecze tygodnia
- **Value Bets** — wykryte zakłady z dodatnim edge względem fair odds
- **Historical Bets** — historia zakładów z wynikami i yield
- **Historia meczów** — wyniki i xG z poprzednich sezonów (`fixtures_history`) jako baza pod model ML
- **Featury pod XGBoost** — rolling statystyki drużyn liczone bez wycieku danych (`xgb_features`)

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
├── xgb_model.py                # Feature engineering pod model XGBoost
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

## Dane historyczne i featury (ręcznie, poza Airflow)

```bash
python fixtures_history.py   # pobiera historię meczów do tabeli fixtures_history
python xgb_model.py          # buduje featury i zapisuje je do tabeli xgb_features
```

`xgb_model.py` bierze 12 lig z dobrym pokryciem xG, uzupełnia brakujące xG golami i dla każdego meczu tworzy 2 wiersze (perspektywa gospodarza i gościa) z:

- formą drużyny i rywala z ostatnich 5 i 10 meczów (xG, gole, W/D/L, BTTS),
- liczbą rozegranych meczów (wiersz powstaje dopiero, gdy obie drużyny mają ≥ 10 meczów w sezonie).

Featury liczone są per sezon, wyłącznie z meczów rozegranych **przed** danym spotkaniem.
