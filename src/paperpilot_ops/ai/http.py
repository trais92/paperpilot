"""Ein kleiner, austauschbarer HTTP-Baustein auf Basis von `urllib` (keine Zusatzpakete).

Adapter bekommen eine `Transport`-Funktion übergeben. Im Betrieb ist das `urllib_transport`,
in Tests eine Attrappe, die Antworten vorgibt. So läuft kein Test über das Netz.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None
    timeout: float = 30.0

    def __repr__(self) -> str:  # Kopfzeilen enthalten den Schlüssel, Inhalt die Mail
        return f"HttpRequest({self.method} {self.url})"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


Transport = Callable[[HttpRequest], HttpResponse]


class TransportError(OSError):
    """Keine Verbindung (DNS, Zeitüberschreitung, TLS). HTTP-Fehlercodes sind keine `TransportError`."""


def urllib_transport(request: HttpRequest) -> HttpResponse:
    """Führt die Anfrage mit der Standardbibliothek aus. HTTP-Fehler werden als Antwort zurückgegeben."""
    req = urllib.request.Request(request.url, data=request.body, method=request.method, headers=dict(request.headers))
    try:
        with urllib.request.urlopen(req, timeout=request.timeout) as resp:  # noqa: S310 (nur https-URLs aus providers.py)
            return HttpResponse(resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as err:
        return HttpResponse(err.code, err.read() or b"", {k.lower(): v for k, v in (err.headers or {}).items()})
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise TransportError(type(err).__name__) from None
