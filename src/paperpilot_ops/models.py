"""Datenmodelle: Mail, Klassifizierung, geplante Aktionen."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes


@dataclass(frozen=True)
class Mail:
    id: str
    date: datetime
    sender: str  # z. B. 'Talent Team <jobs@nordlicht.example>'
    subject: str
    body: str
    attachments: tuple[Attachment, ...] = ()

    @property
    def sender_name(self) -> str:
        return parseaddr(self.sender)[0]

    @property
    def sender_address(self) -> str:
        return parseaddr(self.sender)[1].lower()

    @property
    def sender_domain(self) -> str:
        addr = self.sender_address
        return addr.split("@", 1)[1] if "@" in addr else ""

    @property
    def text(self) -> str:
        """Betreff + Text, kleingeschrieben, fuer die Klassifizierung."""
        return f"{self.subject}\n{self.body}".lower()


@dataclass(frozen=True)
class Classification:
    label: str  # z. B. 'bewerbung/einladung', 'privat/versicherungen', 'werbung', 'unklar'
    confidence: float
    reason: str = ""

    @property
    def group(self) -> str:
        return self.label.split("/", 1)[0]

    @property
    def subtype(self) -> str:
        return self.label.split("/", 1)[1] if "/" in self.label else ""


@dataclass(frozen=True)
class Completion:
    """Antwort eines Sprachmodells (Port `LanguageModel`)."""

    text: str
    provider: str  # welcher Anbieter tatsächlich geantwortet hat
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Deadline:
    date: datetime
    has_time: bool
    context: str
    mail_id: str
    title: str


@dataclass
class PlannedFile:
    path: str  # relativ zum Ablage-Ordner
    content: bytes
    sha256: str


@dataclass
class MailPlan:
    """Was mit einer Mail passieren soll. Wird erst mit --apply ausgefuehrt."""

    mail: Mail
    classification: Classification
    action: str  # 'file' | 'ignore' | 'review' | 'duplicate' | 'skip' (Kategorie nicht gewählt)
    files: list[PlannedFile] = field(default_factory=list)
    table: str = ""  # Übersichtstabelle, in die die Mail nach dem Ablegen eingetragen wird
    deadlines: list[Deadline] = field(default_factory=list)
    notify: bool = False
    company: str = ""
