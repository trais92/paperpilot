"""Angaben aus Mail und Anhang (Betrag, Belegdatum, Nummer, Frist) und ihre strenge Prüfung.

Die KI liefert Vorschläge, der Mensch kann sie im Browser korrigieren. Beide Wege laufen durch
dieselben Prüfungen: Was nicht eindeutig passt, wird verworfen und bleibt leer (Regel 5),
statt eine geratene Angabe in die Übersicht zu schreiben.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import Fields

__all__ = [
    "FIELD_LABELS",
    "FIELD_NAMES",
    "FieldError",
    "check_amount",
    "check_date",
    "check_reference",
    "parse_fields",
    "parse_form_fields",
]

FIELD_NAMES = ("amount", "document_date", "reference", "due_date")
FIELD_LABELS = {"amount": "Betrag", "document_date": "Belegdatum", "reference": "Nummer", "due_date": "Frist"}

MAX_AMOUNT = Decimal("10000000")
MAX_REFERENCE_CHARS = 40
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./_-]*")
_AMOUNT = re.compile(r"(-?\d+(?:[.,]\d{1,2})?)\s*([A-Z]{3})")


class FieldError(ValueError):
    """Eine Angabe hat nicht das erwartete Format. Die Meldung nennt das Feld, nicht den Wert."""


def check_amount(value: object, currency: object = "EUR") -> str:
    """Betrag als `1234.56 EUR`. Zahl oder Text wie `49,90 EUR`."""
    if isinstance(value, bool):
        raise FieldError("Betrag ist keine Zahl.")
    if isinstance(value, int | float):
        text = f"{value} {currency}"
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise FieldError("Betrag ist keine Zahl.")
    match = _AMOUNT.fullmatch(text)
    if not match:
        raise FieldError("Betrag braucht die Form 49.90 EUR.")
    try:
        amount = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        raise FieldError("Betrag ist keine Zahl.") from None
    if not -MAX_AMOUNT < amount < MAX_AMOUNT:
        raise FieldError("Betrag ist unplausibel groß.")
    return f"{amount.quantize(Decimal('0.01'))} {match.group(2)}"


def check_date(value: object, name: str = "Datum") -> str:
    """Datum als `JJJJ-MM-TT`, zwischen 2000 und 2100."""
    if not isinstance(value, str):
        raise FieldError(f"{name} ist kein Text.")
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        raise FieldError(f"{name} braucht die Form JJJJ-MM-TT.") from None
    if not 2000 <= parsed.year <= 2100:
        raise FieldError(f"{name} liegt außerhalb von 2000 bis 2100.")
    return parsed.isoformat()


def check_reference(value: object) -> str:
    """Rechnungs-, Kunden- oder Vertragsnummer: ein Wort aus Buchstaben, Ziffern und . / _ -."""
    if not isinstance(value, str):
        raise FieldError("Nummer ist kein Text.")
    text = value.strip()
    if len(text) > MAX_REFERENCE_CHARS or not _REFERENCE.fullmatch(text):
        raise FieldError(f"Nummer: höchstens {MAX_REFERENCE_CHARS} Zeichen, nur Buchstaben, Ziffern und . / _ -.")
    return text


def parse_fields(raw: object) -> tuple[Fields, list[str]]:
    """Prüft das Objekt `fields` einer KI-Antwort. Liefert die gültigen Angaben und die verworfenen Felder.

    Erwartet `amount` (Zahl), `currency` (ISO-Code), `document_date`, `reference`, `due_date`;
    `null` oder fehlend heißt „nicht erkannt“.
    """
    if not isinstance(raw, Mapping):
        return Fields(), ([] if raw is None else ["fields"])
    values: dict[str, str] = {}
    rejected: list[str] = []
    currency = raw.get("currency") or "EUR"
    checks: dict[str, Callable[[object], str]] = {
        "amount": lambda v: check_amount(v, currency),
        "document_date": lambda v: check_date(v, "Belegdatum"),
        "reference": check_reference,
        "due_date": lambda v: check_date(v, "Frist"),
    }
    for name, check in checks.items():
        value = raw.get(name)
        if value is None or value == "":
            continue
        try:
            values[name] = check(value)
        except FieldError:
            rejected.append(FIELD_LABELS[name])
    return Fields(**values), rejected


def parse_form_fields(form: Mapping[str, str], prefix: str) -> Fields:
    """Angaben aus einem Formular (`<prefix>amount` usw.). Leere Felder bleiben leer, Fehler werfen `FieldError`."""
    get = {name: form.get(f"{prefix}{name}", "").strip() for name in FIELD_NAMES}
    return Fields(
        amount=check_amount(get["amount"]) if get["amount"] else "",
        document_date=check_date(get["document_date"], "Belegdatum") if get["document_date"] else "",
        reference=check_reference(get["reference"]) if get["reference"] else "",
        due_date=check_date(get["due_date"], "Frist") if get["due_date"] else "",
    )
