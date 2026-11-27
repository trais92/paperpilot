# Konfiguration (`rules.toml`)

Alles, was PaperPilot entscheidet, steht in einer TOML-Datei: welche KI gefragt wird, welche Kategorien es gibt und wohin sie abgelegt werden. Ohne `--rules` wird die mitgelieferte [`default_rules.toml`](../src/paperpilot_ops/default_rules.toml) verwendet. `paperpilot init` kopiert sie als `rules.toml` zum Anpassen.

## Persönliche Einstellungen (`settings.toml`)

Was der Einrichtungsassistent (`paperpilot setup`) abfragt, landet nicht in der Regeldatei, sondern in einer eigenen kleinen Datei ([ADR 0010](adr/0010-persoenliche-einstellungen.md)):

| System | Ort |
|---|---|
| Windows | `%APPDATA%\PaperPilot\settings.toml` |
| macOS | `~/Library/Application Support/PaperPilot/settings.toml` |
| Linux | `~/.config/paperpilot/settings.toml` (bzw. `$XDG_CONFIG_HOME`) |

`PAPERPILOT_CONFIG_DIR` legt einen anderen Ordner fest. Inhalt, falls von Hand bearbeitet:

```toml
[storage]
target = "local"          # oder "drive"
target_dir = "D:/Ablage"
drive_folder = "PaperPilot"

[categories]              # true = ablegen, false = nur im Postfach lassen
"bewerbung/absage" = false
```

Reihenfolge: Regeldatei, darüber `settings.toml`, darüber die Kommandozeile (`--storage`, `--target`). Gilt für `run` und `eval`, nicht für `demo`. Zugangsdaten stehen nie hier, sondern im Schlüsselbund.

Stichwörter werden kleingeschrieben verglichen und als Teilstring gesucht (`"termin"` trifft auch „Terminbestätigung“).

## `[general]`

| Feld | Typ | Standard | Bedeutung |
|---|---|---|---|
| `target_dir` | String | `"ablage"` | Ablage-Ordner, wenn `--target` fehlt |
| `min_score` | Zahl | `2.0` | Darunter wird `unklar` vergeben |
| `notify_on` | Liste | Einladung, Rückfrage, Angebot, Absage | Labels, die im Bericht unter MELDEN stehen |
| `review_folder` | String | `"00 Eingang"` | Ziel für unklare Mails |
| `tracker` | String | `"Bewerbungen/tracker.csv"` | Pfad des Trackers, relativ zur Ablage |
| `generic_domains` | Liste | gmail.com, gmx.de, web.de, … | Hier wird der Anzeigename statt der Domain als Absender genutzt |

## `[storage]`

| Feld | Typ | Standard | Bedeutung |
|---|---|---|---|
| `target` | String | `"local"` | `"local"`: Ordner aus `target_dir` bzw. `--target`. `"drive"`: Google Drive (vorher `paperpilot login --google`) |
| `drive_folder` | String | `"PaperPilot"` | Wurzelordner in „Meine Ablage“, ein einzelner Name ohne `/` |

`paperpilot run --storage local|drive` überschreibt `target` für einen Lauf. Einrichtung: [google-drive.md](google-drive.md).

## `[ai]`

| Feld | Typ | Standard | Bedeutung |
|---|---|---|---|
| `provider` | String | `"groq"` | Anbieter, der zuerst gefragt wird: `groq` (kostenlos) oder `claude` (**kostenpflichtig**, eigener Schlüssel) |
| `fallback` | Liste | `[]` | Reserve, der Reihe nach. Anbieter ohne Schlüssel werden übersprungen |
| `min_confidence` | Zahl 0–1 | `0.6` | Darunter wird `unklar` vergeben |
| `reserve_models` | Bool | `true` | Ist das Kontingent des ersten Modells erschöpft, fragt PaperPilot mit demselben Schlüssel ein zweites kostenloses Modell des Anbieters (Groq: `openai/gpt-oss-120b`, [ADR 0012](adr/0012-zweites-groq-modell-als-reserve.md)) |
| `read_pdfs` | Bool | `true` | Text von PDF-Anhängen mitsenden (braucht `pip install ".[pdf]"`); `false` lässt Anhänge auf dem Rechner |
| `[ai.models]` | Tabelle | – | Optional ein anderes Modell je Anbieter, z. B. `groq = "openai/gpt-oss-120b"` |

Unbekannte Anbieter oder eine Sicherheit außerhalb von 0 bis 1 sind ein Fehler beim Laden. Anbieter und Einrichtung: [ai-providers.md](ai-providers.md).

## `[groups.<name>]`

Eine Gruppe ist eine Vorbedingung für zusammengehörige Kategorien.

| Feld | Bedeutung |
|---|---|
| `keywords` | Mindestens eines muss treffen, sonst bekommen alle Kategorien der Gruppe Score 0 |
| `folder` | Standard-Zielordner der Gruppe, z. B. `"Bewerbungen/{company}"` |
| `enabled` | `false` schaltet alle Kategorien der Gruppe ab, auch `<gruppe>/sonstiges` |

## `[[categories]]`

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `label` | ja | Eindeutiger Name, Konvention `gruppe/untertyp` oder `bereich/thema` |
| `description` | empfohlen | Ein Satz, was in diese Kategorie gehört. Danach richtet sich die KI. Fehlt er, bekommt die KI die ersten Stichwörter als Hinweis |
| `keywords` | nein | Stichwörter für Vorfilter und Regel-Klassifizierer |
| `senders` | nein | Teilstrings der Absenderadresse, zählen stark (×3) |
| `group` | nein | Zugehörige Gruppe |
| `folder` | nein | Zielordner, sonst der Ordner der Gruppe, sonst `review_folder` |
| `enabled` | nein | `false`: Mails dieser Kategorie werden erkannt, aber nicht abgelegt (Bericht: „nicht gewählt“). Standard `true` |
| `action` | nein | `"file"` (Standard) oder `"ignore"`. Kategorien mit `ignore` bilden den Vorfilter: Was die Regeln dort einordnen, geht nicht an die KI |

### Platzhalter in `folder`

| Platzhalter | Ersetzt durch | Beispiel |
|---|---|---|
| `{company}` | Firmen-/Absendername aus der Domain | `Kranich-Logistik` |
| `{year}` | Jahr des Mail-Datums | `2026` |

## Übersichtstabellen

Jeder Zielordner bekommt eine Übersichtstabelle, in die jede abgelegte Mail eine Zeile schreibt. Sie liegt im festen Teil des Ordnerpfads, also vor dem ersten Platzhalter:

| `folder` | Übersicht |
|---|---|
| `06 Rechnungen & Belege/{year}` | `06 Rechnungen & Belege/Übersicht.csv` |
| `Bewerbungen/{company}` | `Bewerbungen/Übersicht.csv` |
| `00 Eingang` (unklare Mails) | `00 Eingang/Übersicht.csv` |

Spalten: `Datum`, `Absender`, `Betreff`, `Kategorie`, `Betrag`, `Belegdatum`, `Nummer`, `Frist`, `Dateien`, `Begründung`, `Mail-ID`. Betrag, Belegdatum und Nummer liest die KI aus Mail und PDF-Anhang ([ADR 0011](adr/0011-angaben-aus-mail-und-pdf.md)); beim Regel-Klassifizierer bleiben sie leer. Lokal ist das eine CSV-Datei mit Semikolon und UTF-8 mit BOM, die Excel und LibreOffice per Doppelklick richtig öffnen. Zeilen werden nur angehängt, nie geändert oder gelöscht. Kommen Spalten hinzu, werden sie in bestehenden Tabellen hinten angefügt.

## Scoring (Regel-Klassifizierer)

Gilt für den Vorfilter, für `--classifier rules` und für die Demo.

Für jede Mail und jede Kategorie:

```
score = 2 × (Stichwörter im Betreff) + 1 × (Stichwörter nur im Text) + 3 × (Treffer in senders)
```

Für Kategorien mit `group`:

```
score = Gruppen-Score + eigener Score    wenn beide > 0
score = 0                                sonst
```

Trifft eine Gruppe, aber keiner ihrer Untertypen, entsteht `<gruppe>/sonstiges` mit dem Gruppen-Score und dem Gruppenordner als Ziel.

Entscheidung:

1. Kategorien nach Score sortieren. Bei Gleichstand gewinnt ein Label aus `notify_on`.
2. Bester Score < `min_score` → `unklar`.
3. `confidence = bester / (bester + zweitbester)`. Das ist ein Maß für den Abstand, keine Wahrscheinlichkeit.

Den Grund jeder Entscheidung zeigt der Bericht (z. B. `Score 5, naechster 2`).

## Beispiele

**Neue Kategorie für Arztrechnungen** (vor `privat/rechnungen` einfügen, damit sie bei Gleichstand nicht verliert, oder spezifischere Stichwörter wählen):

```toml
[[categories]]
label = "privat/gesundheit"
folder = "08 Gesundheit/{year}"
description = "Arztrechnungen, Rezepte und Post der Krankenkasse."
keywords = ["praxis", "arztrechnung", "krankenkasse", "rezept", "heil- und kostenplan"]
```

Für die KI genügt die Beschreibung; die Stichwörter braucht nur der Regel-Klassifizierer.

**Newsletter eines bestimmten Absenders immer ignorieren:**

```toml
[[categories]]
label = "werbung"
action = "ignore"
keywords = ["newsletter", "abmelden"]
senders = ["news@lieblingsshop.example"]
```

**Strenger werden** (mehr an den Menschen geben, weniger Fehlablagen): `min_score = 3.0`.

## Änderungen prüfen

Nach jeder Regeländerung:

```bash
paperpilot eval --rules rules.toml
paperpilot run --rules rules.toml --source imap      # Trockenlauf ansehen
```

Wenn die Genauigkeit sinkt, zeigt die Liste „Fehlklassifiziert“, welche Mails sich verschoben haben.
