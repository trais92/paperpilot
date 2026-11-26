"""Fristen und Termine aus Mailtext erkennen und als Kalenderdatei (.ics) exportieren."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import Deadline, Mail

TRIGGERS = ("bis", "frist", "spätestens", "termin", "fällig", "zahlbar", "gespräch", "interview", "kündigung", " am ")
_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?(?!\d)")
_TIME = re.compile(r"^\s*(?:,\s*)?(?:um\s+)?(\d{1,2})[:.](\d{2})\s*(?:uhr)?", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    # Satzende = Satzzeichen + Leerraum + Grossbuchstabe. Punkte in "03.12.2026" bleiben unberuehrt.
    parts = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÄÖÜ])", text)
    return [p.strip() for p in parts if p and p.strip()]


def extract_deadlines(mail: Mail) -> list[Deadline]:
    found: dict[datetime, Deadline] = {}
    for sentence in _sentences(mail.body):
        low = f" {sentence.lower()} "
        if not any(t in low for t in TRIGGERS):
            continue
        for m in _DATE.finditer(sentence):
            day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
            if year is None:
                y = mail.date.year
            else:
                y = int(year) + (2000 if len(year) == 2 else 0)
            try:
                dt = datetime(y, month, day)
            except ValueError:
                continue
            if year is None and dt.date() < mail.date.date():
                dt = dt.replace(year=y + 1)
            t = _TIME.match(sentence[m.end() :])
            has_time = False
            if t and int(t.group(1)) < 24 and int(t.group(2)) < 60:
                dt = dt.replace(hour=int(t.group(1)), minute=int(t.group(2)))
                has_time = True
            if dt.date() < mail.date.date():
                continue  # Vergangenheit ist keine Frist
            found.setdefault(dt, Deadline(dt, has_time, sentence[:200], mail.id, mail.subject))
    return sorted(found.values(), key=lambda d: d.date)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def to_ics(deadlines: list[Deadline], now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//agentic-personal-ops//DE", "CALSCALE:GREGORIAN"]
    for d in deadlines:
        uid = f"{d.mail_id}-{d.date:%Y%m%d%H%M}@agentic-personal-ops"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
        if d.has_time:
            end = d.date + timedelta(hours=1)
            lines += [f"DTSTART:{d.date:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{d.date:%Y%m%d}", f"DTEND;VALUE=DATE:{d.date + timedelta(days=1):%Y%m%d}"]
        lines += [f"SUMMARY:{_esc(d.title)}", f"DESCRIPTION:{_esc(d.context)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
