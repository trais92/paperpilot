# CLAUDE.md – Übergabe und Arbeitsregeln

Diese Datei ist der Einstieg für jede Weiterentwicklung (Mensch oder KI-Agent). Sie beschreibt den Stand, die Regeln und die nächsten Schritte. Sprache im Projekt: Deutsch (Code-Bezeichner Englisch).

## Was PaperPilot ist

Eine Python-CLI, die Mails klassifiziert, Mails und Anhänge nach Namenskonvention ablegt, Fristen als `.ics` exportiert, einen Bewerbungs-Tracker pflegt und die Trefferquote auf einem Testset misst. Schwerpunkte: nachvollziehbare Architektur (Ports und Adapter, ADRs), Human-in-the-loop und Messbarkeit. Überblick: [README.md](README.md), Details: [docs/](docs/), Entscheidungen: [docs/adr/](docs/adr/README.md).

Ziel (siehe [docs/roadmap.md](docs/roadmap.md)): Eine fest eingebaute KI erkennt Kategorie und Angaben jeder Mail, abgelegt wird in einer Ordnerstruktur aus wählbaren Kategorien, lokal oder in Google Drive, bedienbar ohne Terminal über eine lokale Seite im Browser.

## Stand (v0.1.0 + Phase 0, 26.11.2026)

- Kern fertig und getestet: Quellen (JSON, IMAP lesend), Regel-Klassifizierer, Namenskonvention, Fristen + iCalendar, Ablage mit Duplikat-Index und Lauf-Stand, Tracker, Bericht, Evaluation, CLI (`demo`, `run`, `eval`, `init`).
- Phase 0 (Architektur-Grundlage) erledigt: Ports in `ports.py` (`MailSource`, `Classifier`, `StorageTarget`, `CredentialStore`), `MemoryStore`, `EnvCredentialStore`, Vertragstest für Ablageziele, ADR 0001 bis 0006.
- 40 Tests grün, Abdeckung 92 %, `ruff` und `mypy --strict` sauber. CI auf Python 3.11 bis 3.13 prüft zusätzlich Format, Abdeckung ≥ 85 %, Demo-Lauf und `eval --min-accuracy 0.85`.
- Evaluation Regeln: 90,4 % Label, 94,2 % Gruppe, 11,5 % `unklar` auf 52 Mails. Siehe [docs/evaluation.md](docs/evaluation.md).
- **Nicht verifiziert:** `LLMClassifier` gegen die echte API. Getestet nur mit einem Fake-Client (`tests/test_classify.py`). Der Aufruf nutzt `client.beta.messages.create` mit `output_config.format` (JSON-Schema), `effort: "low"`, Modell `claude-opus-5-5` (über `PAPERPILOT_MODEL` änderbar) sowie `betas=["server-side-fallback-2026-07-01"]` und `fallbacks="default"`. Beim ersten echten Lauf prüfen, ob die installierte `anthropic`-Version diese Parameter akzeptiert. Sonst `fallbacks`/`betas` entfernen und `client.messages.create` nutzen.
- Paketname `paperpilot-ops` (PyPI-Name `paperpilot` ist vergeben), Importpaket `paperpilot_ops`, Befehl `paperpilot`. Repo: `trais92/paperpilot`.

## Nicht verhandelbare Regeln

1. **Keine echten Daten im Repo.** Beispiel- und Testdaten sind erfunden und nutzen `.example`-Domains. Keine realen Namen, Firmen, Adressen, Beträge.
2. **Least Privilege.** Postfach nur lesen (`readonly`, `BODY.PEEK`). Nie Mails senden, verschieben, löschen oder als gelesen markieren. Externe Dienste bekommen das engste mögliche Recht (z. B. Google Drive nur `drive.file`).
3. **Nie überschreiben, nie löschen** in der Ablage. Kollisionen bekommen `-2`, `-3`.
4. **Trockenlauf ist Standard.** Alles mit Seiteneffekt nur bei `--apply`. Neue Seiteneffekte gehören in die Ausführungsphase von `pipeline.run()`, nie in `plan_mail()`.
5. **Unsicher heißt `unklar`.** Jeder Klassifizierer fällt bei Fehlern auf `unklar` zurück, nie auf eine geratene Kategorie. Auch kein stiller Rückfall von der KI auf die Regeln.
6. **Zugangsdaten nur über `CredentialStore`.** Dauerhaft gespeichert werden sie ausschließlich im Schlüsselbund des Betriebssystems ([ADR 0004](docs/adr/0004-zugangsdaten-im-schluesselbund.md)). Nie in Dateien, im Lauf-Stand, in Logs, im Bericht oder in Fehlermeldungen.
7. **Kern bleibt ohne Abhängigkeiten.** Zusätzliche Pakete nur als optionales Extra in `pyproject.toml` (`[project.optional-dependencies]`), mit Import erst in der Funktion.
8. **Kern nur über Ports.** `pipeline.py`, `evaluate.py` und der Bericht hängen nur von `ports.py` ab, nie von einem konkreten Adapter. Ein neuer Adapter besteht den Vertragstest seines Ports (z. B. `tests/test_storage_contract.py`).
9. **Testset nicht auswendig lernen.** Regeln nicht gezielt auf Fehlfälle aus `eval_set.jsonl` anpassen. Für Optimierung zuerst ein separates Dev-/Holdout-Set anlegen.

## Entwickeln und testen

```bash
pip install -e ".[dev]"
pytest -q                               # alle Tests
pytest tests/test_pipeline.py -q        # nur Pipeline
ruff check . && ruff format --check .
mypy                                    # strenge Typprüfung (src/)
pytest --cov=paperpilot_ops             # Abdeckung, CI verlangt ≥ 85 %
paperpilot demo --reset                 # Ende-zu-Ende auf Beispieldaten
paperpilot eval --min-accuracy 0.85     # Qualitätsschwelle wie in der CI
```

Bei Regeländerungen (`default_rules.toml`) immer `paperpilot eval` vorher und nachher vergleichen und die Zahlen in `README.md` und `docs/evaluation.md` aktualisieren, falls sie sich ändern.

## Code-Landkarte

| Datei | Inhalt | Achtung |
|---|---|---|
| `src/paperpilot_ops/ports.py` | Protokolle `MailSource`, `Classifier`, `StorageTarget`, `CredentialStore` | Verträge stehen in den Docstrings, Änderungen brauchen ein ADR |
| `src/paperpilot_ops/credentials.py` | `EnvCredentialStore`, fest vereinbarte Schlüssel `KEYS` | Neue Zugangsdaten zuerst in `KEYS` eintragen |
| `src/paperpilot_ops/cli.py` | Argumente, Unterbefehle, Verdrahtung der Adapter | Demo-/Testdaten über `importlib.resources` |
| `src/paperpilot_ops/pipeline.py` | `plan_mail()` (rein), `run()` (führt aus), `render_report()` | Planen ohne Seiteneffekte halten |
| `src/paperpilot_ops/classify.py` | `RuleClassifier`, `LLMClassifier`, `make_classifier()` | Neue Klassifizierer: Port `Classifier`, in `make_classifier` und CLI-`choices` eintragen |
| `src/paperpilot_ops/config.py` | TOML laden, `Rules.folder_for()` | Unbekannte Gruppe ist ein Fehler beim Laden |
| `src/paperpilot_ops/default_rules.toml` | Standardregeln | Paketdaten, in `pyproject.toml` gelistet |
| `src/paperpilot_ops/deadlines.py` | Fristen, `.ics` | Satz-Split darf Datumspunkte nicht trennen |
| `src/paperpilot_ops/store.py` | `LocalStore`, `MemoryStore`, Tracker, Fristen | Übersichten nur über `read_text`/`write_text`, nie über Pfade; Metadaten in `.paperpilot/` |
| `src/paperpilot_ops/naming.py` | Dateinamen, Firmenname | Ändert sich die Konvention, ändern sich Hashes nicht (Hash über Inhalt) |
| `src/paperpilot_ops/evaluate.py` | Metriken, Bericht | |
| `src/paperpilot_ops/data/` | `demo_inbox.json`, `eval_set.jsonl` | Nur erfundene Daten |

## Nächste Schritte (priorisiert)

Vollständig mit Fertig-Kriterien in [docs/roadmap.md](docs/roadmap.md). Als Nächstes Phase 1:

1. **Zugangsdaten im Schlüsselbund** ([ADR 0004](docs/adr/0004-zugangsdaten-im-schluesselbund.md)): Adapter `KeyringCredentialStore` als optionales Extra `[keyring]`, Speichern nach Abfrage anbieten, Befehl zum Löschen, Tests dass nichts in Dateien oder Logs landet.
2. **KI-Anbindung** ([ADR 0003](docs/adr/0003-ki-fest-eingebaut.md)): OpenAI-kompatibler Client mit der Standardbibliothek (`urllib`) für Mistral (Standard) und Groq (Reserve), Claude über das vorhandene Extra. Antworten gegen erlaubte Labels prüfen. Kontingente und Datenregeln vorher in den offiziellen Unterlagen prüfen.
3. **Wählbare Kategorien mit Übersichtstabelle** ([ADR 0005](docs/adr/0005-ablage-ordnerstruktur-lokal-oder-drive.md)).
4. **Felder aus Mail und PDF auslesen.**
5. **Neues Testset mit Feldern und Dev/Holdout**, Messung je Anbieter.

## Bekannte Schwächen

- Teilstring-Suche ohne Wortgrenzen und ohne Stemming (siehe Fehleranalyse).
- `confidence` ist ein Abstandsmaß, keine kalibrierte Wahrscheinlichkeit.
- IMAP-`SINCE` arbeitet tagesgenau. Der genaue Vergleich passiert danach in Python. Bei sehr großen Postfächern ist der erste Lauf langsam.
- Mails werden als Markdown abgelegt (kein PDF), HTML-only-Mails liefern leeren oder rohen HTML-Text.
- `.ics`-Zeiten sind „floating“ (ohne Zeitzone).

## Arbeitsweise

- Kleine Commits mit deutscher Beschreibung. Jede Funktionsänderung bekommt einen Test.
- Architekturentscheidungen bekommen ein ADR in `docs/adr/` (Vorlage dort). Akzeptierte ADRs werden nicht umgeschrieben, sondern ersetzt.
- Neue Abhängigkeiten nur als optionales Extra, mit Import in der Funktion (Regel 7). Für den Typcheck in `pyproject.toml` unter `[[tool.mypy.overrides]]` eintragen.
- `main` muss immer grün sein. Größere Änderungen über einen Branch und Pull Request.
- README-Beispielausgaben nach Änderungen am Bericht neu erzeugen (`paperpilot demo --reset`).
