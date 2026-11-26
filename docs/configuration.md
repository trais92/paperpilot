# Konfiguration (`rules.toml`)

Alles, was PaperPilot entscheidet, steht in einer TOML-Datei. Ohne `--rules` wird die mitgelieferte [`default_rules.toml`](../src/paperpilot_ops/default_rules.toml) verwendet. `paperpilot init` kopiert sie als `rules.toml` zum Anpassen.

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

## `[groups.<name>]`

Eine Gruppe ist eine Vorbedingung für zusammengehörige Kategorien.

| Feld | Bedeutung |
|---|---|
| `keywords` | Mindestens eines muss treffen, sonst bekommen alle Kategorien der Gruppe Score 0 |
| `folder` | Standard-Zielordner der Gruppe, z. B. `"Bewerbungen/{company}"` |

## `[[categories]]`

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `label` | ja | Eindeutiger Name, Konvention `gruppe/untertyp` oder `bereich/thema` |
| `keywords` | ja | Stichwörter |
| `senders` | nein | Teilstrings der Absenderadresse, zählen stark (×3) |
| `group` | nein | Zugehörige Gruppe |
| `folder` | nein | Zielordner, sonst der Ordner der Gruppe, sonst `review_folder` |
| `action` | nein | `"file"` (Standard) oder `"ignore"` |

### Platzhalter in `folder`

| Platzhalter | Ersetzt durch | Beispiel |
|---|---|---|
| `{company}` | Firmen-/Absendername aus der Domain | `Kranich-Logistik` |
| `{year}` | Jahr des Mail-Datums | `2026` |

## Scoring

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
keywords = ["praxis", "arztrechnung", "krankenkasse", "rezept", "heil- und kostenplan"]
```

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
