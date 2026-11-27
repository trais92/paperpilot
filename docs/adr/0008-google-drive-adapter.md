# 0008: Google-Drive-Adapter mit Standardbibliothek und Anmeldung im Browser

- Status: Akzeptiert
- Datum: 2026-11-27
- Setzt [0005](0005-ablage-ordnerstruktur-lokal-oder-drive.md) für Google Drive um

## Kontext

[ADR 0005](0005-ablage-ordnerstruktur-lokal-oder-drive.md) legt fest: Google Drive ist ein wählbares Ablageziel mit direkter Anmeldung und dem engsten Recht `drive.file`, die Übersichten sind dort Google-Tabellen. Offen war die technische Umsetzung. Randbedingungen: Kern ohne Abhängigkeiten (Regel 7), nie überschreiben oder löschen (Regel 3), Zugangsdaten nur im Schlüsselbund (Regel 6), Tests ohne Netz.

## Optionen

1. Offizielle Google-Bibliotheken (`google-api-python-client`, `google-auth-oauthlib`) als optionales Extra.
2. Die wenigen nötigen REST-Aufrufe und den OAuth-Ablauf mit der Standardbibliothek, über denselben austauschbaren `Transport` wie die KI-Schicht.

Für die Übersicht in Drive:

a. Google-Sheets-API (zweite Schnittstelle, eigene Freischaltung).
b. CSV hochladen und von Drive in eine Google-Tabelle umwandeln lassen; beim Anhängen als CSV exportieren, zusammenführen, Inhalt ersetzen.

## Entscheidung

- **Option 2.** PaperPilot braucht sechs Aufrufe (suchen, Ordner anlegen, hochladen, Inhalt ersetzen, herunterladen, exportieren) und den OAuth-Ablauf. Die Google-Bibliotheken brächten mehrere Pakete mit vielen Unterabhängigkeiten und einen eigenen HTTP-Stack, den Tests nicht über den gemeinsamen `Transport` ersetzen könnten.
- **Anmeldung:** OAuth 2.0 für installierte Apps mit PKCE (S256), `state` und Rückruf auf `http://127.0.0.1:<freier Port>/`. Angefordert wird nur `drive.file`; Google stuft diesen Scope als „nicht sensibel“ ein, PaperPilot sieht damit ausschließlich selbst angelegte Dateien. Das Refresh-Token kommt in den Schlüsselbund, Zugriffstokens leben nur im Speicher.
- **Option b** für die Übersicht: eine Schnittstelle, ein Scope. Ersetzt wird nur der Inhalt von Tabellen, die PaperPilot selbst angelegt hat; der Vertrag (`merge_table`: nichts geht verloren) gilt wie lokal.
- **Keine Lösch- oder Papierkorb-Methode** in `DriveApi`. Ein Test stellt sicher, dass es keine gibt.
- **Metadaten** (Duplikat-Index, Lauf-Stand) liegen wie lokal in `.paperpilot/` unterhalb des Wurzelordners.
- **Vertragstest:** `DriveStore` besteht `tests/test_storage_contract.py` gegen eine Nachbildung der Drive-Schnittstelle (`tests/fake_drive.py`).

## Folgen

- PaperPilot braucht einen OAuth-Client vom Typ „Desktop-App“ in einem Google-Cloud-Projekt. Bis das Programm einen eigenen mitbringt (Roadmap 9), wird er bei `paperpilot login --google` eingegeben. Für eine öffentliche Version ist die einfache OAuth-Prüfung durch Google nötig. Schritte in [docs/google-drive.md](../google-drive.md).
- Die Client-ID ist bei Desktop-Apps nicht geheim; das „Client-Secret“ laut Google ebenfalls nicht im eigentlichen Sinn. Es wird trotzdem wie alle Zugangsdaten im Schlüsselbund gehalten.
- Beim Anhängen an eine Übersicht wird die ganze Tabelle neu hochgeladen. Für private Mengen (Hunderte Zeilen) unproblematisch; bei sehr großen Tabellen wäre die Sheets-API (Option a) schneller.
- Gegen die echte Schnittstelle noch nicht gemessen. Beim ersten echten Lauf prüfen: Inhalt einer Google-Tabelle lässt sich per `uploadType=media` mit `text/csv` ersetzen.
