# Google Drive als Ablageziel

PaperPilot kann statt in einen lokalen Ordner direkt in Google Drive ablegen, ohne die Drive-App. Es entsteht dieselbe Ordnerstruktur wie lokal unter „Meine Ablage/PaperPilot“, die Übersichten sind Google-Tabellen. Architektur: [ADR 0008](adr/0008-google-drive-adapter.md).

## Nutzen

```bash
pip install ".[keyring]"
paperpilot login --google          # Browser öffnet sich, bei Google zustimmen
paperpilot run --storage drive     # Trockenlauf, dann mit --apply ablegen
```

Dauerhaft umstellen in der Konfiguration:

```toml
[storage]
target = "drive"
drive_folder = "PaperPilot"   # Wurzelordner in „Meine Ablage“
```

`paperpilot logout` löscht auch die Google-Anmeldung aus dem Schlüsselbund. Zusätzlich lässt sich der Zugriff jederzeit unter myaccount.google.com → *Sicherheit* → *Drittanbieter-Apps* widerrufen.

## Welche Rechte PaperPilot bekommt

Nur `https://www.googleapis.com/auth/drive.file`. Damit sieht und ändert PaperPilot ausschließlich Dateien und Ordner, die es selbst angelegt hat. Der Rest von Drive bleibt unsichtbar. Google stuft diesen Scope als „nicht sensibel“ ein. Löschen oder in den Papierkorb verschieben kann PaperPilot nicht: Der Code enthält dafür keinen Aufruf.

## Einmalige Einrichtung des OAuth-Clients

Google verlangt, dass jede App, die sich anmeldet, als OAuth-Client registriert ist. Bis PaperPilot einen eigenen Client mitbringt (Roadmap 9), braucht es einen in einem eigenen Google-Cloud-Projekt:

1. In der Google Cloud Console ein Projekt anlegen.
2. Unter *APIs & Dienste* die **Google Drive API** aktivieren.
3. Den **OAuth-Zustimmungsbildschirm** einrichten (Typ „Extern“, App-Name „PaperPilot“), als Scope nur `drive.file` eintragen und das eigene Google-Konto als Testnutzer hinzufügen.
4. Unter *Anmeldedaten* einen **OAuth-Client vom Typ „Desktop-App“** erstellen.
5. Client-ID und Client-Secret bei `paperpilot login --google` eingeben. Beides wird im Schlüsselbund gespeichert.

Für eine öffentliche Version mit eigenem Client verlangt Google die einfache Prüfung der App (bei nicht sensiblen Scopes ohne Sicherheitsaudit).

## Wie die Anmeldung abläuft

1. PaperPilot startet einen kleinen Server, der nur auf `127.0.0.1` lauscht, und öffnet den Browser mit der Anmeldeseite von Google.
2. Nach der Zustimmung schickt Google den Browser mit einem einmaligen Code zurück an diesen Server.
3. PaperPilot prüft `state` (Schutz vor fremden Rückrufen) und tauscht den Code mit dem PKCE-Prüfwert gegen ein Refresh-Token.
4. Das Refresh-Token landet im Schlüsselbund. Bei jedem Lauf wird daraus ein kurzlebiges Zugriffstoken, das nur im Arbeitsspeicher existiert.

## Stand und Quellen

- Scopes der Drive-Schnittstelle und ihre Einstufung: https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- **Noch nicht gegen die echte Schnittstelle gemessen.** Alle Tests laufen gegen eine Nachbildung (`tests/fake_drive.py`). Beim ersten echten Lauf prüfen: Umwandlung von CSV in eine Google-Tabelle beim Hochladen und Ersetzen des Tabelleninhalts per `uploadType=media`.
