"""Kompositionswurzel: der einzige Ort, an dem Ports mit konkreten Adaptern verbunden werden.

Die CLI (und später die Browser-Oberfläche) holt sich hier fertige Objekte. Der Kern
(`pipeline.py`, `evaluate.py`) kennt nur die Ports und bleibt davon unberührt.
"""

from __future__ import annotations

from .ai import AIClassifier, PrefilteredClassifier, build_language_model
from .ai.http import Transport, urllib_transport
from .classify import RuleClassifier
from .config import Rules
from .drive import DriveApi, DriveStore, GoogleSession
from .models import Attachment
from .pdftext import attachment_text
from .ports import Classifier, CredentialStore, StorageTarget
from .store import LocalStore

CLASSIFIERS = ("ai", "rules")


def make_classifier(
    name: str, rules: Rules, creds: CredentialStore | None = None, transport: Transport = urllib_transport
) -> Classifier:
    """`ai`: Vorfilter plus KI (Standard für echte Läufe). `rules`: nur Stichwörter, offline."""
    if name == "rules":
        return RuleClassifier(rules)
    if name == "ai":
        if creds is None:
            raise ValueError("Für den KI-Klassifizierer werden Zugangsdaten gebraucht.")
        model = build_language_model(rules.ai, creds, transport)
        read = attachment_text if rules.ai.read_pdfs else _skip_attachment
        return PrefilteredClassifier(rules, AIClassifier(rules, model, read_attachment=read))
    raise ValueError(f"Unbekannter Klassifizierer: {name}")


def _skip_attachment(attachment: Attachment) -> None:
    """`[ai] read_pdfs = false`: Anhänge bleiben auf dem Rechner."""
    return None


def describe_classifier(classifier: Classifier) -> str:
    """Kurzbeschreibung für den Bericht, z. B. `KI: groq (Vorfilter: Regeln)`."""
    if isinstance(classifier, PrefilteredClassifier) and isinstance(classifier.ai, AIClassifier):
        return f"KI: {classifier.ai.model.name} (Vorfilter: Regeln)"
    if isinstance(classifier, RuleClassifier):
        return "Regeln (ohne KI)"
    return type(classifier).__name__


class MissingGoogleLoginError(RuntimeError):
    """Google Drive ist gewählt, aber es gibt keine gespeicherte Anmeldung."""


def make_store(
    rules: Rules,
    creds: CredentialStore,
    target: str | None = None,
    local_dir: str | None = None,
    transport: Transport = urllib_transport,
) -> StorageTarget:
    """Ablageziel aus `[storage]`, überschreibbar mit `target` (CLI `--storage`) und `local_dir` (`--target`)."""
    chosen = target or rules.storage.target
    if chosen == "local":
        return LocalStore(local_dir or rules.target_dir)
    if chosen == "drive":
        client_id, secret = creds.get("google_client_id"), creds.get("google_client_secret")
        refresh = creds.get("google_refresh_token")
        if not (client_id and secret and refresh):
            raise MissingGoogleLoginError("Google Drive ist gewählt, aber nicht verbunden: paperpilot login --google")
        session = GoogleSession(client_id, secret, refresh, transport)
        return DriveStore(DriveApi(session, transport), rules.storage.drive_folder)
    raise ValueError(f"Unbekanntes Ablageziel: {chosen}")
