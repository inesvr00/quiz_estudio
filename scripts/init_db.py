from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quiz_estudio.db import init_stats_db


def main() -> int:
    init_stats_db()
    print("Tablas de persistencia inicializadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
