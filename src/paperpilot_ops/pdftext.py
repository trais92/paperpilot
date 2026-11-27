"""Text aus PDF-Anhängen, damit die KI Betrag, Nummer und Fristen auch aus der Rechnung lesen kann.

Nutzt das optionale Paket `pypdf` (`pip install "paperpilot-ops[pdf]"`), importiert erst bei Bedarf
(Regel 7). Ohne das Paket werden Anhänge wie bisher nicht gelesen.

Rückgabe von `attachment_text`:
- `None`: kein PDF oder `pypdf` fehlt, über den Inhalt ist nichts bekannt;
- `""`: PDF ohne lesbaren Text (Scan) oder beschädigt;
- sonst der Text, gekürzt auf `max_chars`.
"""

from __future__ import annotations

import io
import logging

from .models import Attachment

__all__ = ["MAX_PDF_PAGES", "attachment_text", "is_pdf"]

MAX_PDF_PAGES = 5  # Rechnungen und Bescheide stehen vorne; begrenzt Laufzeit bei großen Dateien


def is_pdf(attachment: Attachment) -> bool:
    return attachment.filename.lower().endswith(".pdf") or attachment.content.startswith(b"%PDF")


def attachment_text(attachment: Attachment, max_chars: int = 3000) -> str | None:
    if not is_pdf(attachment):
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # Warnungen zu kaputten PDFs nicht ins Terminal
    try:
        reader = PdfReader(io.BytesIO(attachment.content))
        parts: list[str] = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) >= max_chars:
                break
    except Exception:  # beschädigt oder verschlüsselt: wie ein Scan behandeln, der Mensch prüft
        return ""
    return " ".join(" ".join(parts).split())[:max_chars]
