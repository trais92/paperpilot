# Roadmap

Priorisiert nach Nutzen für die Aussagekraft des Projekts. Jeder Punkt nennt ein Kriterium, wann er fertig ist.

## Als Nächstes

| # | Vorhaben | Fertig, wenn |
|---|---|---|
| 1 | **LLM-Klassifizierer mit echtem API-Schlüssel messen** | `paperpilot eval --classifier llm` läuft, Ergebnis und Kosten pro Mail stehen in `docs/evaluation.md` |
| 2 | **Größeres Testset** (≥ 200 Mails, ≥ 10 pro Klasse) mit Holdout | Testset mit `split`-Feld, `eval` berichtet getrennt für Dev und Holdout |
| 3 | **Hybrid-Klassifizierer**: Regeln zuerst, LLM nur bei `unklar` | `--classifier hybrid`, Übergabequote und Kosten im Vergleich dokumentiert |
| 4 | **Konfusionsmatrix und JSON-Report** in `eval` | `paperpilot eval --json report.json`, Matrix im Textbericht |
| 5 | **Stichwort-Normalisierung** (Flexion, Umlaut-Varianten, z. B. „ihre/ihrer bewerbung“) | Nur auf einem neuen Dev-Set entwickelt, Holdout-Ergebnis dokumentiert |

## Danach

| # | Vorhaben | Fertig, wenn |
|---|---|---|
| 6 | Strukturierte Extraktion aus PDF-Anhängen (Betrag, Datum, Vertrags-/Rechnungsnummer) | Felder landen in einer `belege.csv`, Testfälle mit Beispiel-PDFs |
| 7 | Google Drive und Kalender direkt über die APIs statt Sync-Ordner und `.ics` | Optionales Extra `[google]`, OAuth-Anleitung, Trockenlauf unverändert |
| 8 | Lauf-Protokoll (`runs.jsonl`) und kleines HTML-Dashboard | `paperpilot report` erzeugt eine statische Seite mit Läufen, Ablagen, Meldungen |
| 9 | MCP-Server, damit ein KI-Agent PaperPilot als Werkzeug nutzt (`plan`, `apply`, `eval`) | Server startet, `apply` verlangt eine ausdrückliche Bestätigung |
| 10 | Mails als PDF statt Markdown ablegen | Optionales Extra, Standard bleibt abhängigkeitsfrei |
| 11 | Paket auf PyPI veröffentlichen (`paperpilot-ops`) | `pip install paperpilot-ops` funktioniert, Release per GitHub Action |

## Bewusst nicht geplant

- Mails beantworten oder löschen. PaperPilot liest und sortiert, handeln tut der Mensch.
- Zugangsdaten speichern.
- Selbstlernende Regeln ohne Kontrolle. Änderungen an `rules.toml` bleiben menschliche Entscheidungen, die `eval` absichert.
