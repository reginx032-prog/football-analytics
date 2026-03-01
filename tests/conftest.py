"""
conftest.py – ustawia zmienne środowiskowe przed importem config.py,
dzięki czemu testy nie wymagają pliku .env ani połączenia z bazą danych.
"""
import os

# Musi być przed jakimkolwiek importem modułów projektu (w tym config.py)
os.environ.setdefault('API_KEY',     'test_api_key')
os.environ.setdefault('DB_USER',     'test_user')
os.environ.setdefault('DB_PASSWORD', 'test_pass')
os.environ.setdefault('DB_NAME',     'test_db')
os.environ.setdefault('DB_HOST',     'localhost')
os.environ.setdefault('DB_PORT',     '5433')
os.environ.setdefault('SEASON',      '2025')
