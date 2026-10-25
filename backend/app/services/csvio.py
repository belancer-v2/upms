"""CSV helpers shared by every export. UTF-8 with a byte-order mark so Excel opens Bangla text correctly.

Money columns are written as plain decimals in BDT ("1250.50"), built from integer paisa without floats.
"""
import csv
import io
import re
from collections.abc import Iterable, Iterator

from fastapi.responses import StreamingResponse

BOM = "﻿".encode("utf-8")
_SAFE = re.compile(r"^[+-]?\d[\d .,\-]*$")   # numbers and phone numbers can never run as a formula


def bdt(paisa: int | None) -> str:
    """Integer paisa to a decimal BDT string. No float is involved."""
    v = int(paisa or 0)
    sign = "-" if v < 0 else ""
    v = abs(v)
    return f"{sign}{v // 100}.{v % 100:02d}"


def cell(v) -> str:
    """One CSV cell. Text that starts with = + - @ is prefixed with an apostrophe so a spreadsheet never treats it as a formula."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if hasattr(v, "isoformat"):
        return v.isoformat(timespec="seconds") if hasattr(v, "hour") else v.isoformat()
    s = str(v).replace("\r\n", "\n")
    if s and s[0] in "=+-@\t\r" and not _SAFE.match(s):
        return "'" + s
    return s


class _Row:
    def __init__(self):
        self.buf = io.StringIO()
        self.w = csv.writer(self.buf, lineterminator="\r\n")

    def encode(self, row: Iterable) -> bytes:
        self.w.writerow([cell(c) for c in row])
        data = self.buf.getvalue().encode("utf-8")
        self.buf.seek(0)
        self.buf.truncate(0)
        return data


def csv_chunks(headers: list[str], rows: Iterable[Iterable]) -> Iterator[bytes]:
    """The file as a stream of byte chunks: BOM, header line, then one chunk per row."""
    enc = _Row()
    yield BOM
    yield enc.encode(headers)
    for r in rows:
        yield enc.encode(r)


def csv_response(filename: str, headers: list[str], rows: Iterable[Iterable]) -> StreamingResponse:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "export.csv"
    return StreamingResponse(csv_chunks(headers, rows), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "no-store"})


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name or "").strip("-").lower()
    return s or "building"
