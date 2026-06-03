from __future__ import annotations

from quiz_estudio.csv_repository import normalize_text


def test_normalize_text_collapses_whitespace_and_lowercases() -> None:
    assert normalize_text("  Hola\tMundo\nNuevo  ") == "hola mundo nuevo"


def test_normalize_text_removes_quotes_punctuation_and_accents() -> None:
    assert normalize_text('“Cuál es la opción correcta?”') == "cual es la opcion correcta"
