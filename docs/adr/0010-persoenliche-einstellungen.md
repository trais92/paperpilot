# 0010: Einrichtungsassistent speichert persönliche Einstellungen getrennt von den Regeln

- Status: Akzeptiert
- Datum: 2026-11-27
- Umsetzung von Roadmap 8, baut auf [0004](0004-zugangsdaten-im-schluesselbund.md) und [0009](0009-bericht-mit-freigabe-im-browser.md) auf

## Kontext

Der Einrichtungsassistent soll ohne Terminal alles abfragen, was ein erster Lauf braucht: Postfach, KI-Schlüssel, welche Kategorien abgelegt werden, Ablageziel und Zeitplan. Zugangsdaten haben mit dem Schlüsselbund schon ihren Ort (Regel 6). Offen war, wohin die übrigen Wahlen gehen.

Die Regeldatei (`default_rules.toml` bzw. `--rules`) enthält Kategorien mit Beschreibungen, Stichwörtern und Ordnern, mit Kommentaren. Python bringt einen TOML-Leser, aber keinen Schreiber mit (Regel 7: keine Abhängigkeit im Kern).

## Optionen

1. Der Assistent schreibt eine vollständige Regeldatei (Kopie der Standardregeln mit geänderten Werten).
2. Der Assistent schreibt nur die gewählten Werte in eine eigene kleine Datei, die beim Laden über die Regeln gelegt wird.
3. Einstellungen im Schlüsselbund oder in einer Datenbank.

## Entscheidung

**Option 2.** `settings.toml` im Konfigurationsordner des Benutzers enthält nur `[storage]` (Ziel, lokaler Ordner, Drive-Ordner) und `[categories]` (Label = true/false). `settings.apply_settings()` legt sie über die geladenen Regeln.

- Die Regeldatei bleibt unberührt: Kommentare gehen nicht verloren, und neue Kategorien aus einer neuen Version kommen an, statt von einer alten Kopie verdeckt zu werden.
- Die Datei ist so klein, dass ein eigener Schreiber reicht (JSON-Strings sind gültige TOML-Strings). Geschrieben wird atomar über eine temporäre Datei.
- Ordner nach den Gepflogenheiten des Systems: `%APPDATA%\PaperPilot` (Windows), `~/Library/Application Support/PaperPilot` (macOS), `$XDG_CONFIG_HOME/paperpilot` bzw. `~/.config/paperpilot` (Linux). `PAPERPILOT_CONFIG_DIR` übersteuert das (portable Installation, Tests).
- Vorrang: Regeldatei < `settings.toml` < Kommandozeile (`--storage`, `--target`). Die Einstellungen gelten für `run` und `eval`, nicht für `demo`, damit die Demo immer gleich bleibt.
- Eine Kategorie in `settings.toml`, die es in den Regeln nicht gibt, ist ein Fehler beim Laden, wie eine unbekannte Gruppe in der Regeldatei.
- Der Assistent ist eine zweite `LocalPage` neben dem Bericht (ADR 0009) und nutzt denselben Server mit denselben Schutzmaßnahmen. Passwörter und Schlüssel werden geprüft (Postfach: Probe-Anmeldung), in den Schlüsselbund geschrieben und auf der Seite nie wieder angezeigt.
- Den Zeitplan richtet der Assistent nicht selbst ein, sondern zeigt die Befehle für Aufgabenplanung bzw. cron. Einen Systemdienst anzulegen ist ein Eingriff ins Betriebssystem, der zum Installationsprogramm (Roadmap 9) gehört.

## Folgen

- `paperpilot setup` öffnet den Assistenten; „Fertig, ersten Lauf ansehen“ startet danach direkt `run --source imap --browser`.
- Wer lieber Dateien bearbeitet, kann weiter eine eigene Regeldatei pflegen; `settings.toml` darf fehlen.
- Zwei Orte für Konfiguration: Die Doku ([configuration.md](../configuration.md)) beschreibt die Reihenfolge.
- Ganz ohne Terminal geht es erst mit dem Programm zum Doppelklicken (Roadmap 9), das `paperpilot setup` beim ersten Start öffnet.
