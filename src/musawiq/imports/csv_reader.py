"""CSV parsing primitives for imports."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

MAX_DATA_ROWS = 100_000
_UTF8_BOM = b"\xef\xbb\xbf"
_DELIMITER = ","


class CsvError(Exception):
    """Base class for CSV ingestion errors."""


class CsvFormatError(CsvError):
    """Raised when the input is not a usable UTF-8 CSV file."""


class CsvTooLargeError(CsvError):
    """Raised when the file exceeds the data-row limit."""


@dataclass(frozen=True)
class ParsedCsv:
    headers: list[str]
    rows: list[dict[str, str]]
    row_numbers: list[int]
    delimiter: str
    encoding: str
    row_count: int


def _decode(data: bytes) -> tuple[str, str]:
    if not data:
        raise CsvFormatError("CSV file is empty")

    encoding = "utf-8-sig" if data.startswith(_UTF8_BOM) else "utf-8"
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise CsvFormatError("CSV must be valid UTF-8") from exc

    if not text.strip():
        raise CsvFormatError("CSV file is empty")
    return text, encoding


def read_csv(data: bytes) -> ParsedCsv:
    """Parse UTF-8 CSV bytes into headers and row dictionaries.

    Quoted commas and embedded newlines are handled by the stdlib reader.
    Missing trailing fields are normalized to empty strings; extra fields are
    ignored. Business validation and column mapping belong to later modules.
    """
    text, encoding = _decode(data)

    try:
        reader = csv.reader(
            io.StringIO(text, newline=""),
            delimiter=_DELIMITER,
            strict=True,
        )
        header_row = next(reader, None)
        if header_row is None or not any(cell.strip() for cell in header_row):
            raise CsvFormatError("CSV must include a header row")
        if len(set(header_row)) != len(header_row):
            raise CsvFormatError("CSV headers must be unique")

        headers = list(header_row)
        rows: list[dict[str, str]] = []
        row_numbers: list[int] = []

        for row in reader:
            row_number = len(row_numbers) + 1
            if row_number > MAX_DATA_ROWS:
                raise CsvTooLargeError(
                    f"CSV exceeds {MAX_DATA_ROWS} data rows"
                )
            rows.append(
                {
                    header: row[index] if index < len(row) else ""
                    for index, header in enumerate(headers)
                }
            )
            row_numbers.append(row_number)
    except csv.Error as exc:
        raise CsvFormatError(f"Malformed CSV: {exc}") from exc

    return ParsedCsv(
        headers=headers,
        rows=rows,
        row_numbers=row_numbers,
        delimiter=_DELIMITER,
        encoding=encoding,
        row_count=len(rows),
    )


__all__ = [
    "CsvError",
    "CsvFormatError",
    "CsvTooLargeError",
    "MAX_DATA_ROWS",
    "ParsedCsv",
    "read_csv",
]
