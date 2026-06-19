from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_CSV_PATH = Path(
    os.getenv("QUESTIONS_CSV_PATH", PROJECT_ROOT / "preguntas_nuevo_formato.csv")
)
QUESTION_REPOSITORY_BACKEND = os.getenv("QUESTION_REPOSITORY_BACKEND", "csv").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).strip().lower()
IS_PRODUCTION = APP_ENV == "production" or os.getenv("RENDER", "").strip().lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
PAGE_SIZE = 50
ALLOWED_BATCH_SIZES = {1, 10}
BACKUP_DIR = PROJECT_ROOT / "backups"
