"""Dünner HTTP-Server für den Bericht mit Freigabe. Nur Standardbibliothek, kein JavaScript.

Schutzmaßnahmen (docs/security.md, ADR 0009):
- lauscht nur auf 127.0.0.1, Port zufällig;
- jede Seite und jedes Formular verlangt ein Zufallstoken (`secrets.token_urlsafe`), das nur in der
  Adresse steht, die PaperPilot selbst im Browser öffnet; fremde Seiten können es nicht kennen;
- Formulare werden zusätzlich nur von derselben Herkunft angenommen (Origin-Prüfung);
- strenge Content-Security-Policy: keine Skripte, keine fremden Quellen, Formulare nur an sich selbst;
- Adressen werden nicht protokolliert, weil sie das Token enthalten.
"""

from __future__ import annotations

import http.server
import threading
import urllib.parse
from collections.abc import Callable

from .review import ReviewError, ReviewSession

__all__ = ["MAX_FORM_BYTES", "SECURITY_HEADERS", "make_handler", "review_url", "serve"]

MAX_FORM_BYTES = 1_000_000
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class _NotFound(Exception):
    pass


def make_handler(
    session: ReviewSession, on_final_page: Callable[[], None] = lambda: None
) -> type[http.server.BaseHTTPRequestHandler]:
    """Request-Handler für eine Sitzung. `on_final_page` läuft, sobald die Ergebnisseite ausgeliefert ist."""
    lock = threading.Lock()  # zwei gleichzeitige Freigaben dürfen nicht zweimal ausführen

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            url = urllib.parse.urlsplit(self.path)
            token = dict(urllib.parse.parse_qsl(url.query)).get("token")
            if url.path != "/" or token != session.token:
                self._send(404, "Nicht gefunden.")
                return
            self._send(200, session.page(), "text/html; charset=utf-8")
            if session.finished:
                on_final_page()

        def do_POST(self) -> None:  # noqa: N802
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{self.headers.get('Host', '')}":
                self._send(403, "Formular von fremder Seite abgelehnt.")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_FORM_BYTES:
                self._send(413, "Formular zu groß oder ohne Länge.")
                return
            form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode("utf-8", "replace")))
            try:
                with lock:
                    self._dispatch(form)
            except ReviewError as exc:
                self._send(400, str(exc))
                return
            except _NotFound:
                self._send(404, "Nicht gefunden.")
                return
            # Post/Redirect/Get: die Ergebnisseite lässt sich neu laden, ohne erneut abzusenden
            self.send_response(303)
            self.send_header("Location", f"/?token={urllib.parse.quote(session.token)}")
            self.send_header("Content-Length", "0")
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.end_headers()

        def _dispatch(self, form: dict[str, str]) -> None:
            if self.path == "/approve":
                session.approve(form)
            elif self.path == "/cancel":
                session.cancel(form)
            else:
                raise _NotFound

        def _send(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            return  # Adressen enthalten das Token und gehören in kein Protokoll

    return Handler


def review_url(port: int, token: str) -> str:
    return f"http://127.0.0.1:{port}/?token={urllib.parse.quote(token)}"


def serve(
    session: ReviewSession,
    open_browser: Callable[[str], object],
    timeout: float = 1800.0,
    grace: float = 10.0,
) -> ReviewSession:
    """Startet den Server, öffnet den Browser und wartet auf Freigabe, Abbruch oder Zeitablauf.

    Nach dem Ende bleibt der Server höchstens `grace` Sekunden offen, damit der Browser die
    Ergebnisseite noch laden kann. Läuft `timeout` ab, wurde nichts geschrieben.
    """
    finished = threading.Event()
    shown = threading.Event()
    previous = session.on_done

    def on_done() -> None:
        previous()
        finished.set()

    session.on_done = on_done
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session, shown.set))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        open_browser(review_url(server.server_address[1], session.token))
        if finished.wait(timeout):
            shown.wait(grace)
    finally:
        server.shutdown()
        server.server_close()
        session.on_done = previous
    return session
