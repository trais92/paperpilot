# Roadmap

Ziel ist ein Werkzeug, das man ohne Programmierkenntnisse herunterlädt, im Browser einrichtet und das danach selbstständig sortiert: Eine KI erkennt Kategorie und wichtige Angaben jeder Mail, die Dokumente landen in einer geordneten Ordnerstruktur, lokal oder in Google Drive, und jeder Lauf wird vor dem Schreiben freigegeben. Die Entscheidungen dahinter stehen in [docs/adr/](adr/README.md).

Jeder Schritt ist ein eigener Pull Request mit Tests, Doku und, wo nötig, einem ADR. `main` bleibt grün.

## Phase 0: Architektur-Grundlage

| # | Vorhaben | Fertig, wenn | Stand |
|---|---|---|---|
| 0 | Ports für Ablageziel und Zugangsdaten, ADRs, `mypy --strict` und Testabdeckung in der CI | Kern hängt nur von `ports.py` ab, Vertragstest für Ablageziele, ADR 0001 bis 0006 | erledigt |

## Phase 1: KI und Ablage als Kern

| # | Vorhaben | Fertig, wenn | Stand |
|---|---|---|---|
| 1 | Zugangsdaten im Schlüsselbund ([ADR 0004](adr/0004-zugangsdaten-im-schluesselbund.md)) | App-Passwort einmal eingeben, der nächste Lauf fragt nicht; Befehl zum Löschen | erledigt |
| 2 | KI-Anbindung: Groq, Mistral als Reserve, Claude ([ADR 0003](adr/0003-ki-fest-eingebaut.md), [0007](adr/0007-ki-schicht-mit-austauschbaren-modellen.md)) | Eine Mail ergibt Kategorie oder `unklar`; Gratis-Anbieter ohne Zusatzpaket; Antworten werden gegen erlaubte Kategorien geprüft | erledigt, Messung mit echtem Schlüssel offen |
| 3 | Wählbare Kategorien, auch eigene, mit Ordnerstruktur und Übersichtstabelle ([ADR 0005](adr/0005-ablage-ordnerstruktur-lokal-oder-drive.md)) | Demo-Lauf legt nur die gewählten Ordner an und füllt deren Übersicht |
| 4 | KI liest Felder aus Mail und PDF-Anhang aus (Betrag, Datum, Nummer, Fristen) | Felder landen in der Übersicht; gescannte PDFs ohne Text gehen in den Eingang |
| 5 | Neues Testset (≥ 200 erfundene Mails mit Feldern, `split: dev\|holdout`), Messung von Kategorie und Feldern je Anbieter, `eval --json`, Konfusionsmatrix | Zahlen für Regeln, Mistral, Groq und Claude in `docs/evaluation.md` |

## Phase 2: Bedienung ohne Terminal

| # | Vorhaben | Fertig, wenn |
|---|---|---|
| 6 | Bericht mit Freigabe als lokale Seite im Browser | „Freigeben“ ersetzt `--apply`; Angaben lassen sich vorher korrigieren |
| 7 | Google Drive als Ablageziel mit direkter Anmeldung, Übersicht als Google-Tabelle | Derselbe Lauf legt in Drive dieselbe Struktur an wie lokal; Vertragstest grün |
| 8 | Einrichtungsassistent im Browser: Postfach, Kategorien, KI-Schlüssel, Ablageziel, Zeitplan | Neuer Rechner bis zum ersten Lauf ohne Terminal |
| 9 | Programm für Windows und macOS, Veröffentlichung auf PyPI (`paperpilot-ops`) | Download, Doppelklick, Assistent öffnet sich; Release per GitHub Action |

## Phase 3: Demo-Seite und Erweiterungen

| # | Vorhaben | Fertig, wenn |
|---|---|---|
| 10 | Demo-Seite ohne Installation (statische Seite aus einem Demo-Lauf) | Link im README zeigt Bericht, Ordnerstruktur und Messwerte |
| 11 | Connector (MCP) für die Claude-App | Claude kann einen Lauf planen; abgelegt wird erst nach ausdrücklicher Bestätigung |
| – | Später: Termine direkt in Google Kalender, Mails als PDF ablegen | wird bei Bedarf eingeplant |

## Entfallen

- **Hybrid-Klassifizierer** (Regeln zuerst, KI nur bei `unklar`) und **Stichwort-Normalisierung**: Die KI übernimmt das Sortieren, die Regeln sind nur noch Vorfilter ([ADR 0003](adr/0003-ki-fest-eingebaut.md)).
- **Import von `.eml`/`mbox`**: IMAP bleibt die einzige Quelle für echte Mails ([ADR 0006](adr/0006-imap-als-einzige-mailquelle.md)).

## Bewusst nicht geplant

- Mails beantworten, verschieben oder löschen. PaperPilot liest und sortiert, handeln tut der Mensch.
- Zugangsdaten in Dateien speichern. Erlaubt ist nur der Schlüsselbund des Betriebssystems.
- Lokale KI-Modelle.
- Ausführen ohne Freigabe. Auch automatische Läufe zeigen erst einen Plan.
