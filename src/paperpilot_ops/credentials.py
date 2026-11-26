"""Zugangsdaten über den Port `CredentialStore`.

Heute gibt es einen Adapter, der Umgebungsvariablen liest. Ein Adapter für den
Schlüsselbund des Betriebssystems folgt (docs/adr/0004-zugangsdaten-im-schluesselbund.md).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Fest vereinbarte Schlüssel und die Umgebungsvariable, aus der sie heute gelesen werden.
KEYS: Mapping[str, str] = {
    "imap_host": "PAPERPILOT_IMAP_HOST",
    "imap_user": "PAPERPILOT_IMAP_USER",
    "imap_password": "PAPERPILOT_IMAP_PASSWORD",
}


class EnvCredentialStore:
    """Liest Zugangsdaten aus Umgebungsvariablen. Speichert nichts.

    `environ` ist austauschbar, damit Tests ohne echte Umgebung auskommen.
    """

    def __init__(self, environ: Mapping[str, str] | None = None):
        self._environ = os.environ if environ is None else environ

    def get(self, key: str) -> str | None:
        if key not in KEYS:
            raise KeyError(f"Unbekannter Zugangsdaten-Schlüssel: {key}")
        return self._environ.get(KEYS[key]) or None
