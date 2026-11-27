"""Anmeldung mit Google: OAuth 2.0 für installierte Apps mit PKCE und Rückruf auf 127.0.0.1.

Ablauf von `paperpilot login --google`:

1. PaperPilot öffnet einen kleinen Server auf `127.0.0.1` (zufälliger freier Port) und den Browser
   mit der Google-Anmeldeseite. Angefordert wird nur `drive.file`.
2. Nach der Zustimmung leitet Google zu `http://127.0.0.1:<port>/` mit einem einmaligen Code um.
   `state` schützt vor fremden Rückrufen, PKCE davor, dass ein abgefangener Code nutzbar ist.
3. Der Code wird gegen ein Refresh-Token getauscht, das im Schlüsselbund landet (ADR 0004).

Im Betrieb tauscht `GoogleSession` das Refresh-Token bei Bedarf gegen ein kurzlebiges Zugriffstoken.
Tokens erscheinen nie in Meldungen oder `repr()`.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from ..ai.http import HttpRequest, Transport, TransportError, urllib_transport

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class OAuthError(RuntimeError):
    """Anmeldung bei Google fehlgeschlagen. Die Meldung enthält keine Tokens."""


@dataclass(frozen=True)
class PkcePair:
    verifier: str
    challenge: str


def pkce_pair() -> PkcePair:
    """Zufälliger `code_verifier` und die zugehörige `code_challenge` (S256, RFC 7636)."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return PkcePair(verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"))


def authorization_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": DRIVE_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",  # liefert ein Refresh-Token für spätere Läufe ohne Browser
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(query)}"


def _token_request(transport: Transport, form: dict[str, str]) -> dict[str, object]:
    request = HttpRequest(
        "POST",
        TOKEN_URL,
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        urllib.parse.urlencode(form).encode("ascii"),
    )
    try:
        response = transport(request)
    except TransportError as err:
        raise OAuthError(f"Google nicht erreichbar ({err})") from None
    try:
        data = json.loads(response.body)
    except ValueError:
        data = {}
    if response.status != 200 or not isinstance(data, dict):
        error = data.get("error", "unbekannt") if isinstance(data, dict) else "unbekannt"
        raise OAuthError(f"Google hat die Anmeldung abgelehnt (HTTP {response.status}, {error})")
    return data


def exchange_code(
    client_id: str, client_secret: str, code: str, verifier: str, redirect_uri: str, transport: Transport
) -> str:
    """Tauscht den Code aus dem Rückruf gegen ein Refresh-Token."""
    data = _token_request(
        transport,
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    token = data.get("refresh_token")
    if not isinstance(token, str) or not token:
        raise OAuthError("Google hat kein Refresh-Token geliefert.")
    return token


class GoogleSession:
    """Liefert gültige Zugriffstokens aus einem Refresh-Token und erneuert sie bei Ablauf."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.time,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._transport = transport
        self._clock = clock
        self._access_token: str | None = None
        self._expires_at = 0.0

    def __repr__(self) -> str:
        return "GoogleSession()"

    def access_token(self) -> str:
        if self._access_token is None or self._clock() >= self._expires_at - 60:
            data = _token_request(
                self._transport,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                raise OAuthError("Google hat kein Zugriffstoken geliefert.")
            expires_in = data.get("expires_in", 3600)
            self._access_token = token
            self._expires_at = self._clock() + (float(expires_in) if isinstance(expires_in, int | float) else 3600.0)
        return self._access_token

    def invalidate(self) -> None:
        """Nach einem 401 aufrufen; der nächste Zugriff holt ein neues Token."""
        self._access_token = None


# -- Rückruf im Browser ------------------------------------------------------------------------

_DONE_PAGE = (
    b"<!doctype html><meta charset='utf-8'><title>PaperPilot</title>"
    b"<p style='font-family:sans-serif'>Anmeldung abgeschlossen. Dieses Fenster kann geschlossen werden.</p>"
)


def receive_code(state: str, open_browser: Callable[[str], object], build_url: Callable[[str], str]) -> tuple[str, str]:
    """Startet den Rückruf-Server, öffnet den Browser und wartet auf genau einen Rückruf.

    Gibt `(code, redirect_uri)` zurück. Der Server lauscht nur auf 127.0.0.1.
    """
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (Name von BaseHTTPRequestHandler vorgegeben)
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            result.update(params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_DONE_PAGE)

        def log_message(self, format: str, *args: object) -> None:  # Code nicht ins Terminal schreiben
            return

    with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
        open_browser(build_url(redirect_uri))
        server.timeout = 300
        server.handle_request()
    if result.get("state") != state:
        raise OAuthError("Rückruf passt nicht zur Anfrage (state). Bitte erneut versuchen.")
    if "code" not in result:
        raise OAuthError(f"Anmeldung abgebrochen ({result.get('error', 'kein Code')}).")
    return result["code"], redirect_uri


def login(
    client_id: str,
    client_secret: str,
    open_browser: Callable[[str], object],
    transport: Transport = urllib_transport,
    receive: Callable[..., tuple[str, str]] = receive_code,
) -> str:
    """Kompletter Anmeldeablauf. Gibt das Refresh-Token zurück (zum Speichern im Schlüsselbund)."""
    pkce, state = pkce_pair(), secrets.token_urlsafe(24)
    code, redirect_uri = receive(
        state, open_browser, lambda uri: authorization_url(client_id, uri, pkce.challenge, state)
    )
    return exchange_code(client_id, client_secret, code, pkce.verifier, redirect_uri, transport)
