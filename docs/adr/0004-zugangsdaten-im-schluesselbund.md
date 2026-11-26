# 0004: Zugangsdaten im Schlüsselbund des Betriebssystems

- Status: Akzeptiert
- Datum: 2026-11-26
- Ersetzt die Regel „Zugangsdaten nie speichern“ aus Version 0.1.0

## Kontext

Bisher werden IMAP-Benutzer und App-Passwort bei jedem Lauf aus Umgebungsvariablen gelesen oder abgefragt und nie gespeichert. Für geplante Läufe (9 und 21 Uhr) ohne Mensch am Rechner braucht PaperPilot die Zugangsdaten aber dauerhaft, dazu kommt künftig ein Schlüssel für den KI-Anbieter. Umgebungsvariablen dauerhaft einzurichten ist für Menschen ohne Programmierkenntnisse zu schwer und legt die Werte oft im Klartext in Profil-Dateien ab.

## Optionen

1. Weiterhin nie speichern, Umgebungsvariablen oder Abfrage.
2. Verschlüsselte Datei mit einem Master-Passwort.
3. Schlüsselbund des Betriebssystems (Windows-Anmeldeinformationsverwaltung, macOS-Schlüsselbund, Secret Service unter Linux) über das Paket `keyring`.

## Entscheidung

Zugangsdaten werden einmal eingegeben und im Schlüsselbund des Betriebssystems gespeichert (Option 3). Gelesen werden sie ausschließlich über den Port `CredentialStore` ([0002](0002-ports-und-adapter.md)).

Ein Master-Passwort (Option 2) bräuchte wieder eine Eingabe bei jedem Lauf und eine eigene Verschlüsselung, die man sicher bauen und prüfen müsste. Der Schlüsselbund ist dafür gemacht, an das Benutzerkonto gebunden und wird vom Betriebssystem geschützt.

## Folgen

- `keyring` wird ein optionales Extra (`pip install paperpilot-ops[keyring]`) und ist im fertigen Programm für Windows und macOS enthalten. Der Kern bleibt ohne Abhängigkeiten.
- Zugangsdaten landen nie in Dateien, im Lauf-Stand, in Logs, im Bericht oder in Fehlermeldungen. Das prüfen Tests.
- `EnvCredentialStore` bleibt für CI und Server ohne Schlüsselbund.
- Fehlende Werte werden weiterhin abgefragt. Der Schlüsselbund-Adapter bietet an, sie zu speichern; die Abfrage im Terminal speichert nichts.
- Ein Befehl zum Löschen der gespeicherten Zugangsdaten gehört dazu.
