"""Zugangsdaten über den Port `CredentialStore` (docs/adr/0004-zugangsdaten-im-schluesselbund.md).

Drei Adapter, die sich kombinieren lassen:

- `EnvCredentialStore` liest Umgebungsvariablen und speichert nichts (CI, Server, kurze Tests).
- `KeyringCredentialStore` liest und speichert im Schlüsselbund des Betriebssystems (Alltag am eigenen Rechner).
- `ChainedCredentialStore` fragt mehrere Adapter nacheinander; so überschreibt die Umgebung den Schlüsselbund.

Sicherheitsregeln, die für jeden Adapter gelten und getestet werden:

- Werte stehen nie in `repr()`, Fehlermeldungen, Dateien, Lauf-Stand oder Bericht.
- Nur fest vereinbarte Schlüssel (`KEYS`). Ein unbekannter Schlüssel ist ein Programmierfehler (`KeyError`).
- Der Schlüsselbund wird über das optionale Paket `keyring` angesprochen und erst bei Bedarf importiert.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol, cast

from .ports import CredentialStore

__all__ = [
    "KEYRING_SERVICE",
    "KEYS",
    "ChainedCredentialStore",
    "CredentialStoreError",
    "EnvCredentialStore",
    "KeyringCredentialStore",
    "default_credential_store",
    "keyring_store_or_none",
]

# Fest vereinbarte Schlüssel und die Umgebungsvariable, aus der `EnvCredentialStore` sie liest.
KEYS: Mapping[str, str] = {
    "imap_host": "PAPERPILOT_IMAP_HOST",
    "imap_user": "PAPERPILOT_IMAP_USER",
    "imap_password": "PAPERPILOT_IMAP_PASSWORD",
    "groq_api_key": "PAPERPILOT_GROQ_API_KEY",
    "claude_api_key": "PAPERPILOT_CLAUDE_API_KEY",
    "google_client_id": "PAPERPILOT_GOOGLE_CLIENT_ID",
    "google_client_secret": "PAPERPILOT_GOOGLE_CLIENT_SECRET",
    "google_refresh_token": "PAPERPILOT_GOOGLE_REFRESH_TOKEN",
}

# Name, unter dem PaperPilot seine Einträge im Schlüsselbund ablegt.
KEYRING_SERVICE = "paperpilot"


class CredentialStoreError(RuntimeError):
    """Der Speicher für Zugangsdaten ist nicht nutzbar. Die Meldung enthält nie einen Wert."""


def _check_key(key: str) -> None:
    if key not in KEYS:
        raise KeyError(f"Unbekannter Zugangsdaten-Schlüssel: {key}")


class EnvCredentialStore:
    """Liest Zugangsdaten aus Umgebungsvariablen. Speichert nichts.

    `environ` ist austauschbar, damit Tests ohne echte Umgebung auskommen.
    """

    def __init__(self, environ: Mapping[str, str] | None = None):
        self._environ = os.environ if environ is None else environ

    def __repr__(self) -> str:
        return "EnvCredentialStore()"

    def get(self, key: str) -> str | None:
        _check_key(key)
        return self._environ.get(KEYS[key]) or None


class KeyringBackend(Protocol):
    """Die drei Funktionen des Pakets `keyring`, die PaperPilot nutzt. In Tests durch eine Attrappe ersetzt."""

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringCredentialStore:
    """Zugangsdaten im Schlüsselbund des Betriebssystems.

    Windows: Anmeldeinformationsverwaltung, macOS: Schlüsselbund, Linux: Secret Service.
    Jeder Schlüssel aus `KEYS` ist ein Eintrag unter dem Dienst `paperpilot`.

    `backend` ist austauschbar (Tests). Ohne Angabe wird das Paket `keyring` geladen;
    fehlt es, entsteht ein `CredentialStoreError` mit Installationshinweis.
    """

    def __init__(self, backend: KeyringBackend | None = None, service: str = KEYRING_SERVICE):
        self._backend = backend if backend is not None else _load_keyring()
        self._service = service

    def __repr__(self) -> str:
        return f"KeyringCredentialStore(service={self._service!r})"

    def get(self, key: str) -> str | None:
        _check_key(key)
        try:
            return self._backend.get_password(self._service, key) or None
        except Exception as exc:  # Fehler des Betriebssystems, nie mit Wert in der Meldung
            raise CredentialStoreError(f"Schlüsselbund nicht lesbar ({type(exc).__name__}).") from None

    def set(self, key: str, value: str) -> None:
        _check_key(key)
        if not value:
            raise ValueError(f"Leerer Wert für {key} wird nicht gespeichert.")
        try:
            self._backend.set_password(self._service, key, value)
        except Exception as exc:
            raise CredentialStoreError(f"Schlüsselbund nicht beschreibbar ({type(exc).__name__}).") from None

    def delete(self, key: str) -> bool:
        """Löscht den Eintrag. `True`, wenn es einen gab."""
        if self.get(key) is None:
            return False
        try:
            self._backend.delete_password(self._service, key)
        except Exception as exc:
            raise CredentialStoreError(f"Eintrag nicht löschbar ({type(exc).__name__}).") from None
        return True


def _load_keyring() -> KeyringBackend:
    try:
        import keyring  # optionales Extra: pip install "paperpilot-ops[keyring]"
    except ImportError:
        raise CredentialStoreError(
            'Das Paket "keyring" fehlt. Installieren mit: pip install "paperpilot-ops[keyring]"'
        ) from None
    backend = keyring.get_keyring()
    if backend.priority <= 0:  # Platzhalter-Backend: kein Schlüsselbund auf diesem System
        raise CredentialStoreError(f"Kein Schlüsselbund auf diesem System gefunden ({type(backend).__name__}).")
    return cast(KeyringBackend, keyring)


class ChainedCredentialStore:
    """Fragt mehrere Adapter der Reihe nach und liefert den ersten vorhandenen Wert."""

    def __init__(self, *stores: CredentialStore):
        self._stores = stores

    def __repr__(self) -> str:
        return f"ChainedCredentialStore({', '.join(map(repr, self._stores))})"

    def get(self, key: str) -> str | None:
        _check_key(key)
        for store in self._stores:
            value = store.get(key)
            if value:
                return value
        return None


def keyring_store_or_none() -> KeyringCredentialStore | None:
    """Schlüsselbund, falls installiert und auf diesem System vorhanden, sonst `None`."""
    try:
        return KeyringCredentialStore()
    except CredentialStoreError:
        return None


def default_credential_store(environ: Mapping[str, str] | None = None) -> CredentialStore:
    """Umgebungsvariablen zuerst (CI, Server, bewusste Übersteuerung), danach der Schlüsselbund."""
    env = EnvCredentialStore(environ)
    vault = keyring_store_or_none()
    return env if vault is None else ChainedCredentialStore(env, vault)
