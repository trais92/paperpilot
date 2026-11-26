"""Mail-Quellen: Demo-Postfach (JSON) und echtes Postfach per IMAP (nur lesend)."""

from __future__ import annotations

import base64
import email
import imaplib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol

from .models import Attachment, Mail


class MailSource(Protocol):
    def fetch(self, since: datetime | None) -> Iterator[Mail]: ...


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def mail_from_dict(d: dict) -> Mail:
    atts = []
    for a in d.get("attachments", []):
        raw = base64.b64decode(a["base64"]) if "base64" in a else a.get("text", "").encode("utf-8")
        atts.append(Attachment(a["filename"], raw))
    return Mail(
        id=d["id"],
        date=datetime.fromisoformat(d["date"]),
        sender=d["from"],
        subject=d["subject"],
        body=d.get("body", ""),
        attachments=tuple(atts),
    )


class JsonSource:
    """Liest Mails aus einer JSON-Datei (Liste) oder JSONL. Fuer Demo und Tests."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[dict]:
        text = self.path.read_text("utf-8")
        if self.path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return json.loads(text)

    def fetch(self, since: datetime | None = None) -> Iterator[Mail]:
        for d in self.load():
            m = mail_from_dict(d)
            if since is None or m.date > since:
                yield m


def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value))) if value else ""


def _body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")


class ImapSource:
    """Echtes Postfach, strikt nur lesend (EXAMINE statt SELECT, BODY.PEEK).

    Fuer Gmail: IMAP aktivieren und ein App-Passwort verwenden.
    Zugangsdaten kommen aus Umgebungsvariablen und werden nie gespeichert.
    """

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX"):
        self.host, self.user, self.password, self.folder = host, user, password, folder

    def fetch(self, since: datetime | None = None) -> Iterator[Mail]:
        with imaplib.IMAP4_SSL(self.host) as conn:
            conn.login(self.user, self.password)
            conn.select(self.folder, readonly=True)  # = EXAMINE, nichts wird als gelesen markiert
            criteria = f'(SINCE "{since:%d-%b-%Y}")' if since else "ALL"
            _, data = conn.search(None, criteria)
            for num in data[0].split():
                _, parts = conn.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(parts[0][1])
                date = _naive(parsedate_to_datetime(msg["Date"])) if msg["Date"] else datetime.now()
                if since and date <= since:
                    continue
                atts = tuple(
                    Attachment(_decode(p.get_filename()), p.get_payload(decode=True) or b"")
                    for p in msg.walk()
                    if p.get_filename()
                )
                yield Mail(
                    id=(msg["Message-ID"] or f"imap-{num.decode()}").strip("<>"),
                    date=date,
                    sender=_decode(msg["From"]),
                    subject=_decode(msg["Subject"]),
                    body=_body(msg),
                    attachments=atts,
                )
