"""Ablage im Dateisystem mit Duplikat-Index, Lauf-Status, Tracker und Fristenliste.

Der Ablage-Ordner kann ein lokal synchronisierter Cloud-Ordner sein
(z. B. Google Drive for Desktop), dann landet alles automatisch in der Cloud.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .deadlines import to_ics
from .models import Deadline

META_DIR = ".paperpilot"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta = self.root / META_DIR
        self._index: dict[str, str] | None = None

    # -- Duplikat-Index ----------------------------------------------------
    @property
    def index(self) -> dict[str, str]:
        if self._index is None:
            p = self.meta / "index.json"
            self._index = json.loads(p.read_text("utf-8")) if p.exists() else {}
        return self._index

    def has(self, digest: str) -> bool:
        return digest in self.index

    def write_file(self, rel_path: str, content: bytes) -> Path:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        stem, suffix, n = target.stem, target.suffix, 2
        while target.exists():  # nie ueberschreiben
            target = target.with_name(f"{stem}-{n}{suffix}")
            n += 1
        target.write_bytes(content)
        self.index[sha256(content)] = target.relative_to(self.root).as_posix()
        return target

    # -- Lauf-Status (Idempotenz: 'seit letztem Lauf') ----------------------
    def last_run(self) -> datetime | None:
        p = self.meta / "state.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text("utf-8")).get("last_mail_date")
        return datetime.fromisoformat(raw) if raw else None

    def save(self, last_mail_date: datetime | None) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        (self.meta / "index.json").write_text(json.dumps(self.index, indent=1, ensure_ascii=False), "utf-8")
        state = {"last_run": datetime.now().isoformat(timespec="seconds")}
        prev = self.last_run()
        newest = max(filter(None, [prev, last_mail_date]), default=None)
        state["last_mail_date"] = newest.isoformat() if newest else None
        (self.meta / "state.json").write_text(json.dumps(state, indent=1), "utf-8")


TRACKER_FIELDS = ["firma", "status", "letztes_datum", "betreff", "neu_aus_mail"]


def update_tracker(path: Path, company: str, status: str, date: datetime, subject: str, note: str) -> None:
    """Eine Zeile pro Firma. Spalte 'neu_aus_mail' ist die Bruecke zu anderen Tools/Agenten."""
    rows: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    row = next((r for r in rows if r["firma"] == company), None)
    if row is None:
        row = {k: "" for k in TRACKER_FIELDS} | {"firma": company}
        rows.append(row)
    if not row["letztes_datum"] or row["letztes_datum"] <= f"{date:%Y-%m-%d}":
        row.update(status=status, letztes_datum=f"{date:%Y-%m-%d}", betreff=subject)
    row["neu_aus_mail"] = "; ".join(filter(None, [row.get("neu_aus_mail", ""), note]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["firma"].lower()))


DEADLINE_FIELDS = ["datum", "uhrzeit", "titel", "kontext", "mail_id"]


def update_deadlines(folder: Path, new: list[Deadline]) -> None:
    """Fristenliste (CSV) zusammenfuehren und Kalenderdatei (.ics) neu erzeugen."""
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / "fristen.csv"
    items: dict[tuple[str, str, str], Deadline] = {}
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                has_time = bool(r["uhrzeit"])
                dt = datetime.fromisoformat(f"{r['datum']}T{r['uhrzeit'] or '00:00'}")
                d = Deadline(dt, has_time, r["kontext"], r["mail_id"], r["titel"])
                items[(r["mail_id"], r["datum"], r["uhrzeit"])] = d
    for d in new:
        items[(d.mail_id, f"{d.date:%Y-%m-%d}", f"{d.date:%H:%M}" if d.has_time else "")] = d
    ordered = sorted(items.values(), key=lambda d: d.date)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DEADLINE_FIELDS)
        w.writeheader()
        for d in ordered:
            w.writerow(
                {
                    "datum": f"{d.date:%Y-%m-%d}",
                    "uhrzeit": f"{d.date:%H:%M}" if d.has_time else "",
                    "titel": d.title,
                    "kontext": d.context,
                    "mail_id": d.mail_id,
                }
            )
    (folder / "fristen.ics").write_text(to_ics(ordered), "utf-8", newline="")
