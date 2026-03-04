import psycopg2
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = psycopg2.connect(
    host='localhost',
    port=5433,
    dbname='football_data',
    user='admin',
    password='secret_password'
)
cur = conn.cursor()

# Ogolny yield dla kursow <= 2.20
print("=== YIELD ogolny (bookie_odd <= 2.20) ===")
cur.execute("""
SELECT
    COUNT(*) AS zaklady,
    SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) AS wins,
    ROUND(CAST(100.0 * SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) / COUNT(*) AS NUMERIC), 1) AS hit_rate,
    ROUND(CAST(
        100.0 * SUM(CASE WHEN bet_result = 'won' THEN (bookie_odd - 1) ELSE -1 END) / COUNT(*)
    AS NUMERIC), 2) AS yield
FROM historical_bets
WHERE bookie_odd <= 2.20
  AND bet_result IN ('won','lost');
""")
row = cur.fetchone()
print(f"  Zaklady: {row[0]}, Wins: {row[1]}, Hit%: {row[2]}%, Yield: {row[3]}%")

# Per rynek dla kursow <= 2.20
print("\n=== YIELD per rynek (bookie_odd <= 2.20) ===")
cur.execute("""
SELECT
    market,
    COUNT(*) AS zaklady,
    SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) AS wins,
    ROUND(CAST(100.0 * SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) / COUNT(*) AS NUMERIC), 1) AS hit_rate,
    ROUND(CAST(
        100.0 * SUM(CASE WHEN bet_result = 'won' THEN (bookie_odd - 1) ELSE -1 END) / COUNT(*)
    AS NUMERIC), 2) AS yield
FROM historical_bets
WHERE bookie_odd <= 2.20
  AND bet_result IN ('won','lost')
GROUP BY market
ORDER BY yield DESC;
""")
rows = cur.fetchall()
print(f"  {'Rynek':<15} {'Zakl':>6} {'Wins':>6} {'Hit%':>7} {'Yield':>8}")
print(f"  {'-'*47}")
for r in rows:
    print(f"  {r[0]:<15} {r[1]:>6} {r[2]:>6} {str(r[3]):>6}% {str(r[4]):>7}%")

# Dla porownania: yield ALL kursow
print("\n=== YIELD ogolny (WSZYSTKIE kursy) ===")
cur.execute("""
SELECT
    COUNT(*) AS zaklady,
    ROUND(CAST(100.0 * SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) / COUNT(*) AS NUMERIC), 1) AS hit_rate,
    ROUND(CAST(
        100.0 * SUM(CASE WHEN bet_result = 'won' THEN (bookie_odd - 1) ELSE -1 END) / COUNT(*)
    AS NUMERIC), 2) AS yield
FROM historical_bets
WHERE bet_result IN ('won','lost');
""")
row = cur.fetchone()
print(f"  Zaklady: {row[0]}, Hit%: {row[1]}%, Yield: {row[2]}%")

# Sweet spot: edge <= 30% + bookie_odd <= 2.20
print("\n=== YIELD sweet spot: bookie_odd <= 2.20 + edge <= 0.30 ===")
cur.execute("""
SELECT
    market,
    COUNT(*) AS zaklady,
    SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) AS wins,
    ROUND(CAST(100.0 * SUM(CASE WHEN bet_result = 'won' THEN 1 ELSE 0 END) / COUNT(*) AS NUMERIC), 1) AS hit_rate,
    ROUND(CAST(
        100.0 * SUM(CASE WHEN bet_result = 'won' THEN (bookie_odd - 1) ELSE -1 END) / COUNT(*)
    AS NUMERIC), 2) AS yield
FROM historical_bets
WHERE bookie_odd <= 2.20
  AND edge <= 0.30
  AND bet_result IN ('won','lost')
GROUP BY market
ORDER BY yield DESC;
""")
rows = cur.fetchall()
print(f"  {'Rynek':<15} {'Zakl':>6} {'Wins':>6} {'Hit%':>7} {'Yield':>8}")
print(f"  {'-'*47}")
for r in rows:
    print(f"  {r[0]:<15} {r[1]:>6} {r[2]:>6} {str(r[3]):>6}% {str(r[4]):>7}%")

cur.close()
conn.close()
