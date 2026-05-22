from __future__ import annotations

import sys
from typing import Any

from .db import init_stats_db, get_attempt_repository


def main() -> int:
    try:
        init_stats_db()
        repo = get_attempt_repository()

        attempts = repo.get_all_exam_attempts()
        topics_example = repo.get_exam_attempt_topics(0)

        print("init_stats_db(): OK")
        print(f"get_all_exam_attempts() returned {len(attempts)} rows")
        print(f"get_exam_attempt_topics(0) returned {len(topics_example)} rows")

        return 0
    except Exception as exc:
        print("ERROR during simulacro checks:", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
