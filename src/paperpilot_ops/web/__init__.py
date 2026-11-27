"""Lokale Seiten im Browser: Bericht mit Freigabe (ADR 0009).

- `review.py`: `ReviewSession` hält den Plan eines Laufs, rendert die Seite und führt erst nach
  „Freigeben“ aus, mit den Korrekturen des Menschen. Ohne HTTP testbar.
- `server.py`: dünner HTTP-Server auf 127.0.0.1 mit Zufallstoken, ohne JavaScript.
"""

from .review import ReviewSession
from .server import serve

__all__ = ["ReviewSession", "serve"]
