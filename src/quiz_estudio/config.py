from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "preguntas.csv"
DB_PATH = PROJECT_ROOT / "stats.db"
DATABASE_URL = "postgresql://postgres.sidzjtxybrtypdppcfhv:9udtdjMgYbLm1OdH@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
SECRET_KEY = "quiz-estudio-una-clave-larga-random-2026"
APP_PASSWORD = "quiero estudiar"
PAGE_SIZE = 50
ALLOWED_BATCH_SIZES = {1, 10, 20}
BACKUP_DIR = PROJECT_ROOT / "backups"
