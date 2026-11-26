# CLAUDE.md – Übergabe und Arbeitsregeln

Diese Datei ist der Einstieg für jede Weiterentwicklung (Mensch oder KI-Agent). Sie beschreibt den Stand, die Regeln und die nächsten Schritte. Sprache im Projekt: Deutsch (Code-Bezeichner Englisch).

## Was PaperPilot ist

Eine Python-CLI, die Mails nach Regeln klassifiziert, Mails und Anhänge nach Namenskonvention ablegt, Fristen als `.ics` exportiert, einen Bewerbungs-Tracker pflegt und die Trefferquote auf einem Testset misst. Portfolio-Projekt mit Fokus auf nachvollziehbare Architektur, Human-in-the-loop und Messbarkeit. Überblick: [README.md](README.md), Details: [docs/](docs/).

## Stand (v0.1.0, 26.11.2026)

- Kern fertig und getestet: Quellen (JSON, IMAP lesend), Regel-Klassifizierer, Namenskonvention, Fristen + iCalendar, Ablage mit Duplikat-Index und Lauf-Stand, Tracker, Bericht, Evaluation, CLI (`demo`, `run`, `eval`, `init`).
- 20 Tests grün, `ruff` sauber, CI auf Python 3.11 bis 3.13 grün (inkl. Demo-Lauf und `eval --min-accuracy 0.85`).
- Evaluation Regeln: 90,4 % Label, 94,2 % Gruppe, 11,5 % `unklar` auf 52 Mails. Siehe [docs/evaluation.md](docs/evaluation.md).
- **Nicht verifiziert:** `LLMClassifier` gegen die echte API. Getestet nur mit einem Fake-Client (`tests/test_classify.py`). Der Aufruf nutzt `client.beta.messages.create` mit `output_config.format` (JSON-Schema), `effort: "low"`, Modell `claude-opus-5-5` (über `PAPERPILOT_MODEL` änderbar) sowie `betas=["server-side-fallback-2026-07-01"]` und `fallbacks="default"`. Beim ersten echten Lauf prüfen, ob die installierte `anthropic`-Version diese Parameter akzeptiert. Sonst `fallbacks`/`betas` entfernen und `client.messages.create` nutzen.
- Paketname `paperpilot-ops` (PyPI-Name `paperpilot` ist vergeben), Importpaket `paperpilot_ops`, Befehl `paperpilot`. Repo: `trais92/paperpilot`.

## Nicht verhandelbare Regeln

1. **Keine echten Daten im Repo.** Beispiel- und Testdaten sind erfunden und nutzen `.example`-Domains. Keine realen Namen, Firmen, Adressen, Beträge.
2. **Least Privilege.** Postfach nur lesen (`readonly`, `BODY.PEEK`). Nie Mails senden, verschieben, löschen oder als gelesen markieren.
3. **Nie überschreiben, nie löschen** in der Ablage. Kollisionen bekommen `-2`, `-3`.
4. **Trockenlauf ist Standard.** Alles mit Seiteneffekt nur bei `--apply`. Neue Seiteneffekte gehören in die Ausführungsphase von `pipeline.run()`, nie in `plan_mail()`.
5. **Unsicher heißt `unklar`.** Jeder Klassifizierer fällt bei Fehlern auf `unklar` zurück, nie auf eine geratene Kategorie.
6. **Zugangsdaten nie speichern** (nicht in Dateien, nicht im Lauf-Stand, nicht in Logs).
7. **Kern bleibt ohne Abhängigkeiten.** Zusätzliche Pakete nur als optionales Extra in `pyproject.toml` (`[project.optional-dependencies]`), mit Import erst in der Funktion.
8. **Testset nicht auswendig lernen.** Regeln nicht gezielt auf Fehlfälle aus `eval_set.jsonl` anpassen. Für Optimierung zuerst ein separates Dev-/Holdout-Set anlegen.

## Entwickeln und testen

```bash
pip install -e ".[dev]"
pytest -q                               # alle Tests
pytest tests/test_pipeline.py -q        # nur Pipeline
ruff check . && ruff format --check .
paperpilot demo --reset                 # Ende-zu-Ende auf Beispieldaten
paperpilot eval --min-accuracy 0.85     # Qualitätsschwelle wie in der CI
```

Bei Regeländerungen (`default_rules.toml`) immer `paperpilot eval` vorher und nachher vergleichen und die Zahlen in `README.md` und `docs/evaluation.md` aktualisieren, falls sie sich ändern.

## Code-Landkarte

| Datei | Inhalt | Achtung |
|---|---|---|
| `src/paperpilot_ops/cli.py` | Argumente, Unterbefehle | Demo-/Testdaten über `importlib.resources` |
| `src/paperpilot_ops/pipeline.py` | `plan_mail()` (rein), `run()` (führt aus), `render_report()` | Planen ohne Seiteneffekte halten |
| `src/paperpilot_ops/classify.py` | `RuleClassifier`, `LLMClassifier`, `make_classifier()` | Neue Klassifizierer: Protokoll `Classifier`, in `make_classifier` und CLI-`choices` eintragen |
| `src/paperpilot_ops/config.py` | TOML laden, `Rules.folder_for()` | Unbekannte Gruppe ist ein Fehler beim Laden |
| `src/paperpilot_ops/default_rules.toml` | Standardregeln | Paketdaten, in `pyproject.toml` gelistet |
| `src/paperpilot_ops/deadlines.py` | Fristen, `.ics` | Satz-Split darf Datumspunkte nicht trennen |
| `src/paperpilot_ops/store.py` | Ablage, Index, Lauf-Stand, Tracker, Fristen-CSV | Metadaten in `.paperpilot/` |
| `src/paperpilot_ops/naming.py` | Dateinamen, Firmenname | Ändert sich die Konvention, ändern sich Hashes nicht (Hash über Inhalt) |
| `src/paperpilot_ops/evaluate.py` | Metriken, Bericht | |
| `src/paperpilot_ops/data/` | `demo_inbox.json`, `eval_set.jsonl` | Nur erfundene Daten |

## Nächste Schritte (priorisiert)

1. **LLM mit echtem Schlüssel messen:** `pip install -e ".[llm]"`, `ANTHROPIC_API_KEY` setzen, `paperpilot eval --classifier llm`. Ergebnis, Kosten pro Mail (aus `response.usage`) und Laufzeit in `docs/evaluation.md` festhalten. Vorher die Kostenfrage klären (52 Mails sind günstig, größere Sets nicht).
2. **Testset vergrößern** auf ≥ 200 Mails mit Feld `split: dev|holdout`, `evaluate()` getrennt berichten lassen.
3. **Hybrid-Klassifizierer:** Regeln zuerst, LLM nur für `unklar` (`--classifier hybrid`).
4. **`eval --json`** und Konfusionsmatrix.
5. **Stichwort-Normalisierung** (Flexion „ihre/ihrer“, Umlaut-Varianten). Ursache von 3 der 5 aktuellen Fehler, aber nur auf neuem Dev-Set entwickeln.

Weitere Punkte mit Fertig-Kriterien: [docs/roadmap.md](docs/roadmap.md).

## Bekannte Schwächen

- Teilstring-Suche ohne Wortgrenzen und ohne Stemming (siehe Fehleranalyse).
- `confidence` ist ein Abstandsmaß, keine kalibrierte Wahrscheinlichkeit.
- IMAP-`SINCE` arbeitet tagesgenau. Der genaue Vergleich passiert danach in Python. Bei sehr großen Postfächern ist der erste Lauf langsam.
- Mails werden als Markdown abgelegt (kein PDF), HTML-only-Mails liefern leeren oder rohen HTML-Text.
- `.ics`-Zeiten sind „floating“ (ohne Zeitzone).

## Arbeitsweise

- Kleine Commits mit deutscher Beschreibung. Jede Funktionsänderung bekommt einen Test.
- `main` muss immer grün sein. Größere Änderungen über einen Branch und Pull Request.
- README-Beispielausgaben nach Änderungen am Bericht neu erzeugen (`paperpilot demo --reset`).
