# Changelog

## Unveröffentlicht

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
