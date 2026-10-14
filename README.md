# Football Analytics

System do analizy meczów piłkarskich i wykrywania value betów oparty na statystykach

## Architektura

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Compose                       │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│  │  React   │───▶│  Spring  │───▶│   PostgreSQL      │  │
│  │ Frontend │    │   Boot   │    │  (football_data)  │  │
│  │  :80     │    │  :8081   │    │     :5433         │  │
│  └──────────┘    └──────────┘    └──────────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │                  Apache Airflow                  │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │  Pre-match pipeline (piątek 09:00 UTC)  │    │   │
│  │  │  Teams → Standings → Fixtures → Odds    │    │   │
│  │  │  → Bet Engine                           │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │  Result checker (codziennie 23:00 UTC)  │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  Webserver :8082 │ DB (airflow) :5434           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Frontend | React 18, Vite, nginx |
| Backend | Java 21, Spring Boot 4, Hibernate |
| ETL / Pipeline | Python 3.12, pandas, scipy |
| Scheduler | Apache Airflow 2.11.2 |
| Baza danych | PostgreSQL 15 |
| Infrastruktura | Docker Compose |

## Funkcjonalności

- **Tabele ligowe** — aktualne standings z top lig europejskich
- **Nadchodzące mecze** — kursy bukmacherskie na mecze tygodnia
- **Value Bets** — wykryte zakłady z dodatnim edge względem fair odds
- **Historical Bets** — historia zakładów z wynikami i yield

## Jak uruchomić

### Wymagania
- Docker + Docker Compose

### Konfiguracja

Utwórz plik `.env` w głównym katalogu:

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
├── config.py                   # Konfiguracja połączenia z DB
├── docker-compose.yaml
└── requirements.txt
```

## Pipeline

```
Piątek 09:00 UTC (automatycznie)
─────────────────────────────────
collect_teams
    └─▶ collect_standings
            └─▶ collect_fixtures
                    └─▶ collect_upcoming_odds
                                └─▶ run_bet_engine

Codziennie 23:00 UTC
─────────────────────────────────
check_results  (aktualizuje historical_bets)
```

## Logika value betów

Bet Engine porównuje kursy bukmacherskie z kursami fair obliczonymi na podstawie statystyk drużyn (forma, xG, tabela). Zakład jest oznaczany jako value bet gdy:

```
edge = (1 / fair_odd) - (1 / bookmaker_odd) > próg
```
