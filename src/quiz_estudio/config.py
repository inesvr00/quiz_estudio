from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "preguntas.csv"
DB_PATH = PROJECT_ROOT / "stats.db"
SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")
PAGE_SIZE = 50
ALLOWED_BATCH_SIZES = {1, 10, 20}
BACKUP_DIR = PROJECT_ROOT / "backups"
