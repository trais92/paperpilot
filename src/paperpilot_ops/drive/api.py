"""Die Aufrufe der Google-Drive-Schnittstelle v3, die PaperPilot braucht, mit der Standardbibliothek.

Mit dem Scope `drive.file` sieht PaperPilot nur Dateien und Ordner, die es selbst angelegt hat.
Gelöscht oder in den Papierkorb verschoben wird nie etwas (Regel 3): Es gibt dafür keine Methode.
"""

from __future__ import annotations

import json
import secrets
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ..ai.http import HttpRequest, HttpResponse, Transport, TransportError, urllib_transport

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"


class DriveError(RuntimeError):
    """Ein Aufruf an Google Drive ist fehlgeschlagen. Die Meldung enthält keine Tokens."""


class TokenSource(Protocol):
    def access_token(self) -> str: ...

    def invalidate(self) -> None: ...


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str


def quote_query(value: str) -> str:
    """Wert für eine Drive-Suchanfrage in einfachen Anführungszeichen (Backslash und ' maskiert)."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


class DriveApi:
    """Dünne Hülle um die REST-Aufrufe. Bei 401 wird das Zugriffstoken einmal erneuert."""

    def __init__(
        self,
        tokens: TokenSource,
        transport: Transport = urllib_transport,
        boundary: Callable[[], str] = lambda: secrets.token_hex(16),
    ):
        self._tokens = tokens
        self._transport = transport
        self._boundary = boundary

    def __repr__(self) -> str:
        return "DriveApi()"

    # -- Suchen ---------------------------------------------------------------------------------
    def find(self, parent_id: str, name: str) -> DriveFile | None:
        """Erste nicht gelöschte Datei mit genau diesem Namen im Ordner, sonst `None`."""
        query = f"name = {quote_query(name)} and {quote_query(parent_id)} in parents and trashed = false"
        params = {"q": query, "fields": "files(id,name,mimeType)", "pageSize": "10", "spaces": "drive"}
        data = self._json("GET", f"{API}/files?{urllib.parse.urlencode(params)}")
        files = data.get("files", [])
        if not files:
            return None
        first = files[0]
        return DriveFile(first["id"], first["name"], first.get("mimeType", ""))

    # -- Anlegen --------------------------------------------------------------------------------
    def create_folder(self, parent_id: str, name: str) -> str:
        meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        return str(self._json("POST", f"{API}/files?fields=id", json.dumps(meta).encode(), "application/json")["id"])

    def upload(self, parent_id: str, name: str, content: bytes, mime: str, as_mime: str | None = None) -> str:
        """Neue Datei. Mit `as_mime` wandelt Drive beim Hochladen um (z. B. CSV in eine Google-Tabelle)."""
        meta: dict[str, Any] = {"name": name, "parents": [parent_id]}
        if as_mime:
            meta["mimeType"] = as_mime
        boundary = self._boundary()
        body = b"".join(
            [
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
                json.dumps(meta).encode(),
                f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode(),
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        url = f"{UPLOAD}/files?uploadType=multipart&fields=id"
        return str(self._json("POST", url, body, f"multipart/related; boundary={boundary}")["id"])

    # -- Inhalte --------------------------------------------------------------------------------
    def update_content(self, file_id: str, content: bytes, mime: str) -> None:
        """Ersetzt den Inhalt einer Datei, die PaperPilot selbst erzeugt (Übersichten, Lauf-Stand)."""
        self._json("PATCH", f"{UPLOAD}/files/{file_id}?uploadType=media&fields=id", content, mime)

    def download(self, file_id: str) -> bytes:
        return self._call("GET", f"{API}/files/{file_id}?alt=media").body

    def export(self, file_id: str, mime: str) -> bytes:
        query = urllib.parse.urlencode({"mimeType": mime})
        return self._call("GET", f"{API}/files/{file_id}/export?{query}").body

    # -- intern ---------------------------------------------------------------------------------
    def _json(self, method: str, url: str, body: bytes | None = None, content_type: str | None = None) -> Any:
        response = self._call(method, url, body, content_type)
        try:
            return json.loads(response.body)
        except ValueError:
            raise DriveError("Antwort von Google Drive ist kein JSON.") from None

    def _call(self, method: str, url: str, body: bytes | None = None, content_type: str | None = None) -> HttpResponse:
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self._tokens.access_token()}"}
            if content_type:
                headers["Content-Type"] = content_type
            try:
                response = self._transport(HttpRequest(method, url, headers, body, 60.0))
            except TransportError as err:
                raise DriveError(f"Google Drive nicht erreichbar ({err}).") from None
            if response.status == 401:
                if attempt == 1:
                    self._tokens.invalidate()
                    continue
                break
            if response.status >= 400:
                raise DriveError(f"Google Drive meldet HTTP {response.status} bei {method}.")
            return response
        raise DriveError("Google Drive lehnt die Anmeldung ab. Neu anmelden: paperpilot login --google")
