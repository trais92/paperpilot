# Changelog

## Unveröffentlicht

### Angaben aus Mail und PDF (Roadmap 4)

- Die KI liest Betrag, Belegdatum, Rechnungs-/Kundennummer und Frist aus, auch aus dem Text von PDF-Anhängen (optionales Extra `[pdf]`, `[ai] read_pdfs`).
- Jede Angabe wird einzeln geprüft (`fields.py`); Ungültiges bleibt leer und wird in der Begründung genannt. PDFs ohne Text (Scans) gehen ohne KI-Anfrage in den Eingang.
- Übersichten bekommen die Spalten `Betrag`, `Belegdatum`, `Nummer`; die Frist laut KI kommt in den Kalender; der Bericht zeigt einen Abschnitt „ANGABEN“.
- Im Browser-Bericht lassen sich die Angaben vor der Freigabe korrigieren. ADR 0011.

### Einrichtungsassistent im Browser (Roadmap 8)

- `paperpilot setup`: lokale Seite für Postfach (mit Probe-Anmeldung), Groq-Schlüssel, Kategorien, Ablageziel (lokal oder Google Drive inkl. Anmeldung) und Zeitplan-Befehle; danach auf Wunsch direkt der erste Lauf zur Freigabe.
- Persönliche Einstellungen in `settings.toml` im Konfigurationsordner des Systems, über die Regeln gelegt (`settings.py`); Zugangsdaten weiter nur im Schlüsselbund.
- Server der lokalen Seiten verallgemeinert (`web/page.py`, Vertrag `LocalPage`). ADR 0010, Sicherheitskonzept und Konfigurationsdoku erweitert.

### Bericht mit Freigabe im Browser (Roadmap 6)

- `paperpilot run --browser`: lokale Seite mit dem Plan, Kategorien pro Mail korrigierbar, „Freigeben und ablegen“ führt aus, „Abbrechen“ schreibt nichts.
- Ausgeführt wird genau das Gezeigte (`FixedClassifier`), ohne zweite KI-Anfrage; Korrekturen tragen die Begründung „vom Menschen korrigiert“.
- Nur Standardbibliothek, kein JavaScript; 127.0.0.1, Zufallstoken, Origin-Prüfung, strenge CSP. ADR 0009, Sicherheitskonzept erweitert.

### Google Drive als Ablageziel (Roadmap 7)

- `DriveStore`: dieselbe Ordnerstruktur in „Meine Ablage/PaperPilot“, Übersichten als Google-Tabellen, besteht den Vertragstest der Ablageziele.
- `paperpilot login --google`: Anmeldung im Browser (OAuth mit PKCE, Rückruf auf 127.0.0.1), nur Scope `drive.file`, Refresh-Token im Schlüsselbund.
- Konfiguration `[storage]` (`target`, `drive_folder`) und `paperpilot run --storage local|drive`.
- Nur Standardbibliothek; keine Lösch-Methode. ADR 0008, `docs/google-drive.md`, Sicherheitskonzept erweitert.

### Wählbare Kategorien und Übersichtstabellen (Roadmap 3)

- `enabled = false` an Kategorie oder Gruppe: Mails werden erkannt, aber nicht abgelegt (neue Aktion `skip`, im Bericht „NICHT GEWÄHLT“).
- Eigene Kategorien brauchen nur `label`, `description` und `folder`; Stichwörter sind optional.
- Pro Zielordner eine Übersichtstabelle (`Übersicht.csv`, Excel-tauglich) mit einer Zeile pro abgelegter Mail, auch für den Eingang.
- Port `StorageTarget` um `append_rows`/`read_rows` erweitert, Vertragstest ergänzt.

### KI-Schicht (Roadmap 2)

- Die KI ordnet jede Mail ein, die der Vorfilter nicht als Werbung erkannt hat. `paperpilot run` nutzt sie standardmäßig; `--classifier rules` bleibt als Weg ohne KI.
- Anbieter austauschbar über den neuen Port `LanguageModel`: Groq (voreingestellt, kostenloser Tarif ohne Kreditkarte) ohne Zusatzpaket über `urllib`, Claude optional mit eigenem Schlüssel über das Extra `[llm]`. Reserve-Kette bei Ausfall.
- Antworten werden streng geprüft (erlaubte Kategorie, Sicherheit 0 bis 1, Mindestsicherheit `min_confidence`); alles andere wird `unklar`.
- Konfiguration: neuer Abschnitt `[ai]`, Feld `description` je Kategorie; die Standardkategorien haben Beschreibungen.
- `paperpilot login --ai groq|claude` speichert API-Schlüssel im Schlüsselbund.
- Kompositionswurzel `composition.py`; `make_classifier()` ist von `classify.py` dorthin umgezogen.
- Nur kostenlose Anbieter voreingestellt; Mistral nicht aufgenommen, weil die API eine Abrechnung verlangt.
- Entfernt: `LLMClassifier`, `--classifier llm` und die Umgebungsvariable `PAPERPILOT_MODEL` (ersetzt durch `--classifier ai` mit `provider = "claude"` und `[ai.models]`).
- ADR 0007, `docs/ai-providers.md` mit Quellen, KI-Abschnitt im Sicherheitskonzept.

### Zugangsdaten im Schlüsselbund (Roadmap 1)

- `paperpilot login` fragt IMAP-Server, Benutzer und App-Passwort ab, meldet sich zur Probe an und speichert im Schlüsselbund des Betriebssystems. `--status` zeigt, was gespeichert ist, ohne Werte.
- `paperpilot logout` löscht alle gespeicherten Einträge.
- Neue Adapter `KeyringCredentialStore` (optionales Extra `[keyring]`) und `ChainedCredentialStore`; `paperpilot run` liest erst Umgebungsvariablen, dann den Schlüsselbund.
- Neuer Port `MutableCredentialStore` für Speichern und Löschen; der Kern liest weiterhin nur über `CredentialStore`.
- Sicherheitskonzept in `docs/security.md`, jede Zusage mit Test.

### Architektur-Grundlage (Roadmap 0)

Architektur-Grundlage für die nächsten Schritte (Roadmap Phase 0). Verhalten und Ergebnisse der CLI sind unverändert.

- Ports in `ports.py`: `MailSource`, `Classifier`, `StorageTarget`, `CredentialStore`. Pipeline und Evaluation hängen nur noch davon ab.
- Neues Ablageziel `MemoryStore` für Tests; Tracker und Fristen werden über das Ablageziel geschrieben statt über Pfade.
- `EnvCredentialStore`: IMAP-Zugangsdaten werden über den Port gelesen.
- `LocalStore.write_file()` gibt den relativen Pfad zurück (vorher `Path`).
- IMAP: Antworten ohne Inhalt werden übersprungen statt abzubrechen.
- Vertragstest für Ablageziele, Tests für Zugangsdaten und eine Pipeline ohne Dateisystem (40 Tests).
- CI: Formatprüfung, `mypy --strict`, Testabdeckung mindestens 85 %.
- Architekturentscheidungen in `docs/adr/` (0001 bis 0006), Roadmap auf das neue Zielbild umgestellt.

## 0.1.0 – 2026-11-26

Erste Version.

- Mail-Quellen: JSON/JSONL (Demo, Tests) und IMAP strikt lesend
- Regelbasierter Klassifizierer mit zweistufigen Gruppen, `unklar` unter Mindest-Score
- Optionaler LLM-Klassifizierer (Claude API, strukturierte Ausgabe), noch nicht gegen die echte API gemessen
- Ablage nach Namenskonvention `JJJJ-MM-TT_Absender_Thema.ext`, ohne Überschreiben
- Duplikat-Index (SHA-256) und Lauf-Stand für idempotente Läufe
- Fristen- und Terminerkennung, Export als `fristen.csv` und `fristen.ics`
- Bewerbungs-Tracker mit Spalte `neu_aus_mail`
- Evaluation: Genauigkeit, Precision/Recall/F1, Übergabequote; Testset mit 52 Mails
- CLI: `demo`, `run`, `eval`, `init`; CI auf Python 3.11–3.13
