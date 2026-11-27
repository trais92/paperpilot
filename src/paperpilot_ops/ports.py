"""Schnittstellen (Ports) zwischen dem Kern und der Außenwelt.

Der Kern (Planen, Ausführen, Bericht, Evaluation) kennt nur diese Protokolle.
Jede konkrete Technik ist ein austauschbarer Adapter:

- `MailSource`: Mails seit dem letzten Lauf liefern. Adapter: `ImapSource`, `JsonSource`.
- `Classifier`: Kategorie oder `unklar` bestimmen. Adapter: `RuleClassifier`, `AIClassifier`, `PrefilteredClassifier`.
- `LanguageModel`: ein Sprachmodell nach JSON fragen. Adapter: `OpenAICompatibleModel` (Groq),
  `AnthropicModel` (Claude), `FallbackModel` (Reserve-Kette).
- `StorageTarget`: ablegen ohne Überschreiben, Übersichten, Lauf-Stand. Adapter: `LocalStore`, `MemoryStore`.
- `CredentialStore`: Zugangsdaten lesen, nie in Dateien. Adapter: `EnvCredentialStore`,
  `KeyringCredentialStore`, `ChainedCredentialStore`.
- `MutableCredentialStore`: zusätzlich speichern und löschen. Adapter: `KeyringCredentialStore`.

Begründung und geplante Adapter:
docs/adr/0002-ports-und-adapter.md
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from .models import Classification, Completion, Mail


class MailSource(Protocol):
    """Liefert Mails, die neuer als `since` sind. Darf das Postfach nie verändern."""

    def fetch(self, since: datetime | None) -> Iterator[Mail]: ...


class Classifier(Protocol):
    """Ordnet einer Mail genau ein Label zu. Bei jeder Unsicherheit oder Störung: `unklar`."""

    def classify(self, mail: Mail) -> Classification: ...


class ProviderError(Exception):
    """Ein KI-Anbieter hat keine verwertbare Antwort geliefert.

    `kind` ist einer von `network`, `auth`, `rate_limit`, `server`, `refusal`, `invalid_response`.
    Die Meldung enthält nie Mail-Inhalte und nie den API-Schlüssel.
    """

    def __init__(self, provider: str, kind: str, message: str):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.kind = kind


class LanguageModel(Protocol):
    """Ein Sprachmodell, das auf eine Anfrage mit einem JSON-Objekt antwortet.

    Vertrag (geprüft in tests/test_ai_models.py für jeden Adapter):

    - `complete_json` liefert den Antworttext unverändert in `Completion.text`. Ob er gültiges JSON
      nach `schema` ist, prüft der Aufrufer; Adapter dürfen `schema` nutzen, um die Ausgabe einzuschränken.
    - Jede Störung (Netz, Anmeldung, Kontingent, Ablehnung, kaputte Hülle) wird zu `ProviderError`.
      Andere Ausnahmen verlassen den Adapter nicht.
    - Adapter protokollieren keine Inhalte und geben den Schlüssel nie in Meldungen oder `repr()` preis.
    """

    @property
    def name(self) -> str:
        """Kurzname für Bericht und Begründung, z. B. `groq` oder `groq → claude`."""
        ...

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> Completion: ...


class StorageTarget(Protocol):
    """Ablageziel für Dokumente, Übersichten und den Lauf-Stand.

    Vertrag (geprüft in tests/test_storage_contract.py für jeden Adapter):

    - `write_file` überschreibt nie. Bei Namensgleichheit entsteht `name-2.ext`, `name-3.ext`, …
      Rückgabe ist der tatsächlich verwendete relative Pfad.
    - Nach `write_file` meldet `has(sha256(inhalt))` den Inhalt als bekannt (Duplikat-Schutz).
    - `write_text` ersetzt eine Übersichtsdatei (Tracker, Fristen) vollständig. Nur für Dateien,
      die PaperPilot selbst erzeugt; abgelegte Dokumente laufen immer über `write_file`.
    - `read_text` liefert `None`, wenn die Datei nicht existiert.
    - `append_rows` hängt Zeilen an eine Übersichtstabelle an. `table` ist ein relativer Pfad ohne
      Dateiendung; das Format wählt der Adapter (lokal CSV, in Drive eine Google-Tabelle). Fehlt die
      Tabelle, entsteht sie mit `columns`. Neue Spalten kommen hinten dazu, bestehende Zeilen und
      Spalten bleiben erhalten. Fehlende Werte sind leer.
    - `read_rows` liefert alle Zeilen einer Übersichtstabelle, leer, wenn es sie nicht gibt.
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

    def append_rows(self, table: str, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None: ...

    def read_rows(self, table: str) -> list[dict[str, str]]: ...

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
