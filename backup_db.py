#!/usr/bin/env python3
"""Nightly SQLite backup script.

Usage:
    python backup_db.py

Schedule (Windows Task Scheduler):
    - Create Basic Task → Daily → Time: 03:00
    - Action: Start a program
    - Program: python
    - Arguments: C:\path\to\backup_db.py
    - Start in: C:\path\to\Hatiapp_cowork_OPENCODE

Schedule (Linux cron):
    0 3 * * * cd /path/to/app && python3 backup_db.py
"""

import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path("app.db")
BACKUP_DIR = Path("backups")
KEEP_BACKUPS = 7  # keep last N backups


def backup():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"app_{timestamp}.db"

    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}")

    # Clean old backups
    backups = sorted(BACKUP_DIR.glob("app_*.db"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()
        print(f"Removed old backup: {old}")


if __name__ == "__main__":
    backup()
