"""Google Drive als Ablageziel (docs/adr/0005-ablage-ordnerstruktur-lokal-oder-drive.md, 0008).

Nur Standardbibliothek; HTTP läuft über den austauschbaren `Transport` aus `ai/http.py`.

- `oauth.py`: Anmeldung mit Google (OAuth 2.0 für Desktop-Apps, PKCE, Rückruf auf 127.0.0.1),
  Scope ausschließlich `drive.file` (nur von PaperPilot selbst angelegte Dateien).
- `api.py`: die wenigen Aufrufe der Drive-Schnittstelle v3, die PaperPilot braucht.
- `store.py`: `DriveStore`, ein Adapter des Ports `StorageTarget`.
"""

from .api import DriveApi, DriveError
from .oauth import DRIVE_SCOPE, GoogleSession
from .store import DriveStore

__all__ = ["DRIVE_SCOPE", "DriveApi", "DriveError", "DriveStore", "GoogleSession"]
