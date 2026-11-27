"""Schnittstellen (Ports) zwischen dem Kern und der Außenwelt.

Der Kern (Planen, Ausführen, Bericht, Evaluation) kennt nur diese Protokolle.
Jede konkrete Technik ist ein austauschbarer Adapter:

- `MailSource`: Mails seit dem letzten Lauf liefern. Adapter: `ImapSource`, `JsonSource`.
- `Classifier`: Kategorie oder `unklar` bestimmen. Adapter: `RuleClassifier`, `LLMClassifier`.
- `StorageTarget`: ablegen ohne Überschreiben, Übersichten, Lauf-Stand. Adapter: `LocalStore`, `MemoryStore`.
- `CredentialStore`: Zugangsdaten lesen, nie in Dateien. Adapter: `EnvCredentialStore`,
  `KeyringCredentialStore`, `ChainedCredentialStore`.
- `MutableCredentialStore`: zusätzlich speichern und löschen. Adapter: `KeyringCredentialStore`.

Begründung und geplante Adapter (Google Drive, weitere KI-Anbieter):
docs/adr/0002-ports-und-adapter.md
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol

from .models import Classification, Mail


class MailSource(Protocol):
    """Liefert Mails, die neuer als `since` sind. Darf das Postfach nie verändern."""

    def fetch(self, since: datetime | None) -> Iterator[Mail]: ...


class Classifier(Protocol):
    """Ordnet einer Mail genau ein Label zu. Bei jeder Unsicherheit oder Störung: `unklar`."""

    def classify(self, mail: Mail) -> Classification: ...


class StorageTarget(Protocol):
    """Ablageziel für Dokumente, Übersichten und den Lauf-Stand.

    Vertrag (geprüft in tests/test_storage_contract.py für jeden Adapter):

    - `write_file` überschreibt nie. Bei Namensgleichheit entsteht `name-2.ext`, `name-3.ext`, …
      Rückgabe ist der tatsächlich verwendete relative Pfad.
    - Nach `write_file` meldet `has(sha256(inhalt))` den Inhalt als bekannt (Duplikat-Schutz).
    - `write_text` ersetzt eine Übersichtsdatei (Tracker, Fristen) vollständig. Nur für Dateien,
      die PaperPilot selbst erzeugt; abgelegte Dokumente laufen immer über `write_file`.
    - `read_text` liefert `None`, wenn die Datei nicht existiert.
    - `save` merkt sich das Datum der neuesten verarbeiteten Mail; `last_run` geht nie zurück.
    - Pfade sind relativ und nutzen `/` als Trenner, unabhängig vom Betriebssystem.
    """

    @property
    def location(self) -> str:
        """Menschenlesbare Angabe, wo abgelegt wird (für den Bericht)."""
        ...

    def has(self, digest: str) -> bool: ...

    def write_file(self, rel_path: str, content: bytes) -> str: ...

    def read_text(self, rel_path: str) -> str | None: ...

    def write_text(self, rel_path: str, text: str) -> None: ...

    def last_run(self) -> datetime | None: ...

    def save(self, last_mail_date: datetime | None) -> None: ...


class CredentialStore(Protocol):
    """Liest Zugangsdaten. Adapter dürfen sie nie in Dateien, Lauf-Stand oder Logs schreiben.

    Schlüssel sind fest vereinbarte Namen (siehe `credentials.KEYS`). Unbekannte Schlüssel
    sind ein Programmierfehler und lösen `KeyError` aus.
    """

    def get(self, key: str) -> str | None: ...


class MutableCredentialStore(CredentialStore, Protocol):
    """Ein `CredentialStore`, der Werte dauerhaft speichern und löschen kann.

    Erlaubt ist das nur für den Schlüsselbund des Betriebssystems (docs/adr/0004-zugangsdaten-im-schluesselbund.md).
    Nur Befehle, die ein Mensch ausdrücklich aufruft (`paperpilot login`, `paperpilot logout`), nutzen diesen Port;
    der Kern liest ausschließlich über `CredentialStore`.

    - `set` lehnt leere Werte ab (`ValueError`).
    - `delete` liefert `True`, wenn ein Eintrag gelöscht wurde, `False`, wenn keiner da war.
    """

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> bool: ...
