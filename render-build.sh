#!/bin/bash
# Устанавливаем зависимости
pip install Flask==2.3.3 gunicorn==21.2.0 psycopg[binary]==3.2.4

# Или для SQLite:
# pip install Flask==2.3.3 gunicorn==21.2.0