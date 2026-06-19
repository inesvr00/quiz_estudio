from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQLITE_DB_PATH = PROJECT_ROOT / "local_data" / "stats.db"
TABLE_NAME = "question_attempts"
REQUIRED_COLUMNS = (
    "question_id",
    "enunciado",
    "tema",
    "respuesta_correcta",
    "respuesta_usuario",
    "es_correcta",
    "created_at",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra intentos desde SQLite local a PostgreSQL/Supabase.",
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=SQLITE_DB_PATH,
        help="Ruta del stats.db local. Por defecto usa ./local_data/stats.db.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el resumen sin insertar datos en PostgreSQL.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Migra sin pedir confirmacion interactiva.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("Error: configura DATABASE_URL antes de ejecutar la migracion.")
        return 1

    sqlite_path = args.sqlite_path.resolve()
    if not sqlite_path.exists():
        print(f"Error: no existe la base SQLite local: {sqlite_path}")
        return 1

    rows = read_sqlite_attempts(sqlite_path)
    print(f"Base SQLite: {sqlite_path}")
    print(f"Tabla origen: {TABLE_NAME}")
    print(f"Filas leidas desde SQLite: {len(rows)}")

    with psycopg.connect(
        with_default_sslmode(database_url),
        prepare_threshold=None,
    ) as postgres_connection:
        ensure_postgres_table_exists(postgres_connection)
        inserted, skipped = migrate_rows(
            postgres_connection,
            rows,
            dry_run=args.dry_run,
            assume_yes=args.yes,
        )

    print(f"Filas insertadas en PostgreSQL: {inserted}")
    print(f"Filas omitidas por duplicadas: {skipped}")
    if args.dry_run:
        print("Dry run completado: no se insertaron datos.")

    return 0


def read_sqlite_attempts(sqlite_path: Path) -> list[dict[str, Any]]:
    sqlite_uri = sqlite_path.as_uri() + "?mode=ro"
    with sqlite3.connect(sqlite_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        ensure_sqlite_table_exists(connection)
        rows = connection.execute(
            f"""
            SELECT {", ".join(REQUIRED_COLUMNS)}
            FROM {TABLE_NAME}
            ORDER BY id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def ensure_sqlite_table_exists(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (TABLE_NAME,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Error: la base SQLite no contiene la tabla {TABLE_NAME}.")

    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    }
    missing_columns = set(REQUIRED_COLUMNS) - columns
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise SystemExit(f"Error: faltan columnas en SQLite: {missing}.")


def ensure_postgres_table_exists(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (f"public.{TABLE_NAME}",))
        table_name = cursor.fetchone()[0]
        if table_name is None:
            raise SystemExit(
                "Error: no existe la tabla question_attempts en PostgreSQL. "
                "Ejecuta primero scripts/init_db.py o schema.sql.",
            )

        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (TABLE_NAME,),
        )
        columns = {row[0] for row in cursor.fetchall()}

    missing_columns = set(REQUIRED_COLUMNS) - columns
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise SystemExit(f"Error: faltan columnas en PostgreSQL: {missing}.")


def migrate_rows(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool,
    assume_yes: bool,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    seen_in_run = set()

    print("Resumen de migracion:")
    print(f"- Tabla destino: {TABLE_NAME}")
    print("- No se borraran datos en PostgreSQL.")
    print("- La base SQLite se abre en modo solo lectura.")
    print(
        "- Duplicado: mismos question_id, enunciado, tema, respuesta_correcta, "
        "respuesta_usuario, es_correcta y created_at."
    )

    if dry_run:
        print("- Modo: dry run.")
    elif not assume_yes and not confirm_migration():
        print("Migracion cancelada.")
        return 0, 0

    with connection.cursor() as cursor:
        for row in rows:
            key = dedupe_key(row)
            if key in seen_in_run:
                skipped += 1
                continue

            if dry_run:
                if postgres_duplicate_exists(cursor, row):
                    skipped += 1
                else:
                    inserted += 1
                    seen_in_run.add(key)
                continue

            cursor.execute(
                """
                INSERT INTO question_attempts (
                    question_id,
                    enunciado,
                    tema,
                    respuesta_correcta,
                    respuesta_usuario,
                    es_correcta,
                    created_at
                )
                SELECT
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s::timestamptz
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM question_attempts
                    WHERE question_id = %s
                      AND enunciado = %s
                      AND tema = %s
                      AND respuesta_correcta = %s
                      AND respuesta_usuario = %s
                      AND es_correcta = %s
                      AND created_at = %s::timestamptz
                )
                """,
                row_values(row) + row_values(row),
            )
            if cursor.rowcount == 1:
                inserted += 1
                seen_in_run.add(key)
            else:
                skipped += 1

    if dry_run:
        connection.rollback()
    else:
        connection.commit()

    return inserted, skipped


def postgres_duplicate_exists(cursor: psycopg.Cursor, row: dict[str, Any]) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM question_attempts
        WHERE question_id = %s
          AND enunciado = %s
          AND tema = %s
          AND respuesta_correcta = %s
          AND respuesta_usuario = %s
          AND es_correcta = %s
          AND created_at = %s::timestamptz
        LIMIT 1
        """,
        row_values(row),
    )
    return cursor.fetchone() is not None


def row_values(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["question_id"],
        row["enunciado"],
        row["tema"],
        row["respuesta_correcta"],
        row["respuesta_usuario"],
        bool(row["es_correcta"]),
        row["created_at"],
    )


def dedupe_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return row_values(row)


def confirm_migration() -> bool:
    answer = input("Insertar estas filas en PostgreSQL? Escribe 'SI' para continuar: ")
    return answer.strip().upper() == "SI"


def with_default_sslmode(database_url: str) -> str:
    parsed_url = urlparse(database_url)
    query = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    if "sslmode" not in query:
        query["sslmode"] = "require"

    return urlunparse(parsed_url._replace(query=urlencode(query)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nMigracion cancelada.")
        raise SystemExit(130)
