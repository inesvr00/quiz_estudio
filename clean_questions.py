from __future__ import annotations

import csv

from import_questions import deduplicate_main_csv


def main() -> int:
    try:
        summary = deduplicate_main_csv()
    except (FileNotFoundError, ValueError, csv.Error) as error:
        print(f"Error: {error}")
        return 1

    print("Resumen de limpieza")
    print(f"- filas originales: {summary['original_rows']}")
    print(f"- duplicados eliminados: {summary['duplicates_removed']}")
    print(f"- filas finales: {summary['final_rows']}")
    print(f"- backup creado: {summary['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
