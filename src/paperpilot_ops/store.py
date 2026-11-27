"""Ablageziele (Port `StorageTarget`) und die Übersichten Tracker und Fristen.

- `LocalStore` legt in einem Ordner ab. Das kann auch ein synchronisierter Cloud-Ordner sein
  (z. B. Google Drive für den Computer).
- `MemoryStore` hält alles im Speicher, für Tests und Probeläufe.

Tracker und Fristen werden nur über `read_text`/`write_text` geschrieben, damit sie mit jedem
Ablageziel funktionieren. Übersichtstabellen pro Kategorie laufen über `append_rows`/`read_rows`;
lokal sind das CSV-Dateien, die Excel und LibreOffice direkt öffnen (Semikolon, UTF-8 mit BOM).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath

from .deadlines import to_ics
from .models import Deadline
from .ports import StorageTarget

META_DIR = ".paperpilot"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _numbered(rel_path: str, n: int) -> str:
    """'a/b.txt', 2 -> 'a/b-2.txt'"""
    p = PurePosixPath(rel_path)
    return str(p.with_name(f"{p.stem}-{n}{p.suffix}"))


def _newest(*dates: datetime | None) -> datetime | None:
    return max((d for d in dates if d is not None), default=None)


def merge_table(
    existing_columns: Sequence[str],
    existing_rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[str], list[dict[str, str]]]:
    """Vertrag von `append_rows`: Spalten vereinigen (neue hinten), Zeilen anhängen, nichts verlieren."""
    merged = list(dict.fromkeys([*existing_columns, *columns]))
    out = [{c: str(r.get(c, "")) for c in merged} for r in [*existing_rows, *rows]]
    return merged, out


# Lokales Tabellenformat: so öffnet Excel mit deutscher Ländereinstellung die Datei per Doppelklick
# richtig (Spalten getrennt, Umlaute korrekt). LibreOffice erkennt es ebenfalls.
TABLE_SUFFIX = ".csv"
TABLE_DELIMITER = ";"
TABLE_ENCODING = "utf-8-sig"


class LocalStore:
    """Ablage im Dateisystem. Metadaten (Duplikat-Index, Lauf-Stand) liegen in `.paperpilot/`."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta = self.root / META_DIR
        self._index: dict[str, str] | None = None

    @property
    def location(self) -> str:
        return str(self.root.resolve())

    # -- Duplikat-Index ----------------------------------------------------
    @property
    def index(self) -> dict[str, str]:
        if self._index is None:
            p = self.meta / "index.json"
            self._index = json.loads(p.read_text("utf-8")) if p.exists() else {}
        return self._index

    def has(self, digest: str) -> bool:
        return digest in self.index

    def write_file(self, rel_path: str, content: bytes) -> str:
        candidate, n = rel_path, 2
        while (self.root / candidate).exists():  # nie überschreiben
            candidate, n = _numbered(rel_path, n), n + 1
        target = self.root / candidate
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        self.index[sha256(content)] = candidate
        return candidate

    # -- Übersichten (Tracker, Fristen) --------------------------------------
    def read_text(self, rel_path: str) -> str | None:
        p = self.root / rel_path
        if not p.exists():
            return None
        with p.open(encoding="utf-8", newline="") as f:  # Zeilenenden unverändert (CSV, iCalendar)
            return f.read()

    def write_text(self, rel_path: str, text: str) -> None:
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            f.write(text)

    # -- Übersichtstabellen pro Kategorie -----------------------------------
    def read_rows(self, table: str) -> list[dict[str, str]]:
        return self._read_table(table)[1]

    def append_rows(self, table: str, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
        old_columns, old_rows = self._read_table(table)
        merged_columns, merged_rows = merge_table(old_columns, old_rows, columns, rows)
        p = self.root / f"{table}{TABLE_SUFFIX}"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding=TABLE_ENCODING, newline="") as f:
            w = csv.DictWriter(f, fieldnames=merged_columns, delimiter=TABLE_DELIMITER)
            w.writeheader()
            w.writerows(merged_rows)

    def _read_table(self, table: str) -> tuple[list[str], list[dict[str, str]]]:
        p = self.root / f"{table}{TABLE_SUFFIX}"
        if not p.exists():
            return [], []
        with p.open(encoding=TABLE_ENCODING, newline="") as f:
            reader = csv.DictReader(f, delimiter=TABLE_DELIMITER)
            rows = [{k: v or "" for k, v in row.items() if k is not None} for row in reader]
            return list(reader.fieldnames or []), rows

    # -- Lauf-Stand (Idempotenz: 'seit letztem Lauf') ----------------------
    def last_run(self) -> datetime | None:
        p = self.meta / "state.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text("utf-8")).get("last_mail_date")
        return datetime.fromisoformat(raw) if raw else None

    def save(self, last_mail_date: datetime | None) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        (self.meta / "index.json").write_text(json.dumps(self.index, indent=1, ensure_ascii=False), "utf-8")
        newest = _newest(self.last_run(), last_mail_date)
        state = {
            "last_run": datetime.now().isoformat(timespec="seconds"),
            "last_mail_date": newest.isoformat() if newest else None,
        }
        (self.meta / "state.json").write_text(json.dumps(state, indent=1), "utf-8")


class MemoryStore:
    """Ablageziel im Arbeitsspeicher. Erfüllt denselben Vertrag wie `LocalStore`."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.texts: dict[str, str] = {}
        self.tables: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
        self._index: dict[str, str] = {}
        self._last_mail_date: datetime | None = None

    @property
    def location(self) -> str:
        return "Arbeitsspeicher"

    def has(self, digest: str) -> bool:
        return digest in self._index

    def write_file(self, rel_path: str, content: bytes) -> str:
        candidate, n = rel_path, 2
        while candidate in self.files or candidate in self.texts:
            candidate, n = _numbered(rel_path, n), n + 1
        self.files[candidate] = content
        self._index[sha256(content)] = candidate
        return candidate

    def read_text(self, rel_path: str) -> str | None:
        return self.texts.get(rel_path)

    def write_text(self, rel_path: str, text: str) -> None:
        self.texts[rel_path] = text

    def read_rows(self, table: str) -> list[dict[str, str]]:
        return [dict(r) for r in self.tables.get(table, ([], []))[1]]

    def append_rows(self, table: str, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
        old_columns, old_rows = self.tables.get(table, ([], []))
        self.tables[table] = merge_table(old_columns, old_rows, columns, rows)

    def last_run(self) -> datetime | None:
        return self._last_mail_date

    def save(self, last_mail_date: datetime | None) -> None:
        self._last_mail_date = _newest(self._last_mail_date, last_mail_date)


# -- Übersichten --------------------------------------------------------------------

TRACKER_FIELDS = ["firma", "status", "letztes_datum", "betreff", "neu_aus_mail"]
DEADLINE_FIELDS = ["datum", "uhrzeit", "titel", "kontext", "mail_id"]


def _read_csv(store: StorageTarget, rel_path: str) -> list[dict[str, str]]:
    text = store.read_text(rel_path)
    if text is None:
        return []
    return [dict(row) for row in csv.DictReader(io.StringIO(text, newline=""))]


def _write_csv(store: StorageTarget, rel_path: str, fields: list[str], rows: list[dict[str, str]]) -> None:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    store.write_text(rel_path, buf.getvalue())


def update_tracker(
    store: StorageTarget, rel_path: str, company: str, status: str, date: datetime, subject: str, note: str
) -> None:
    """Eine Zeile pro Firma. Spalte 'neu_aus_mail' ist die Brücke zu anderen Werkzeugen."""
    rows = _read_csv(store, rel_path)
    row = next((r for r in rows if r["firma"] == company), None)
    if row is None:
        row = {k: "" for k in TRACKER_FIELDS} | {"firma": company}
        rows.append(row)
    if not row["letztes_datum"] or row["letztes_datum"] <= f"{date:%Y-%m-%d}":
        row.update(status=status, letztes_datum=f"{date:%Y-%m-%d}", betreff=subject)
    row["neu_aus_mail"] = "; ".join(filter(None, [row.get("neu_aus_mail", ""), note]))
    _write_csv(store, rel_path, TRACKER_FIELDS, sorted(rows, key=lambda r: r["firma"].lower()))


def update_deadlines(store: StorageTarget, folder: str, new: list[Deadline]) -> None:
    """Fristenliste (CSV) zusammenführen und Kalenderdatei (.ics) neu erzeugen."""
    items: dict[tuple[str, str, str], Deadline] = {}
    for r in _read_csv(store, f"{folder}/fristen.csv"):
        dt = datetime.fromisoformat(f"{r['datum']}T{r['uhrzeit'] or '00:00'}")
        items[(r["mail_id"], r["datum"], r["uhrzeit"])] = Deadline(
            dt, bool(r["uhrzeit"]), r["kontext"], r["mail_id"], r["titel"]
        )
    for d in new:
        items[(d.mail_id, f"{d.date:%Y-%m-%d}", f"{d.date:%H:%M}" if d.has_time else "")] = d
    ordered = sorted(items.values(), key=lambda d: d.date)
    rows = [
        {
            "datum": f"{d.date:%Y-%m-%d}",
            "uhrzeit": f"{d.date:%H:%M}" if d.has_time else "",
            "titel": d.title,
            "kontext": d.context,
            "mail_id": d.mail_id,
        }
        for d in ordered
    ]
    _write_csv(store, f"{folder}/fristen.csv", DEADLINE_FIELDS, rows)
    store.write_text(f"{folder}/fristen.ics", to_ics(ordered))
