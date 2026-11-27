"""Lokale Seiten im Browser: Bericht mit Freigabe und Einrichtungsassistent (ADR 0009, 0010).

- `page.py`: Vertrag `LocalPage`, Maskierung, Layout und Fehlerarten, die beide Seiten teilen.
- `review.py`: `ReviewSession` hält den Plan eines Laufs, rendert die Seite und führt erst nach
  „Freigeben“ aus, mit den Korrekturen des Menschen. Ohne HTTP testbar.
- `setup.py`: `SetupSession`, der Einrichtungsassistent; speichert Zugangsdaten im Schlüsselbund und
  die übrigen Wahlen in `settings.toml`.
- `server.py`: dünner HTTP-Server auf 127.0.0.1 mit Zufallstoken, ohne JavaScript.
"""

from .review import ReviewSession
from .server import serve
from .setup import SetupSession

__all__ = ["ReviewSession", "SetupSession", "serve"]
