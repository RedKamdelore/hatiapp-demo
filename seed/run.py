"""
Запусти один раз для заполнения базы:
    python seed/run.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import engine
from seed.users import seed_users
from seed.schedule import seed_schedule

if __name__ == "__main__":
    print("🔧 Создаём таблицы...")
    models.Base.metadata.create_all(bind=engine)
    print("✅ Таблицы готовы")
    seed_users()
    seed_schedule()
    print("🎉 База заполнена!")
