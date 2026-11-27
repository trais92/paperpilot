# 0005: Ablage als Ordnerstruktur, lokal oder in Google Drive

- Status: Akzeptiert
- Datum: 2026-11-26

## Kontext

Ergebnis eines Laufs sind heute Dateien in einem lokalen Ordner nach fester Namenskonvention, dazu `tracker.csv` und `fristen.csv`. Google Drive geht nur über einen synchronisierten Ordner, der die Drive-App voraussetzt. Künftig wählen Nutzer selbst, welche Kategorien sortiert werden, können eigene beschreiben ([0003](0003-ki-fest-eingebaut.md)), und die KI liest pro Kategorie Angaben aus. Diese Angaben müssen irgendwo durchsuchbar landen.

## Optionen

1. SQL-Datenbank (SQLite) als zentrales Verzeichnis, Dateien daneben.
2. Ordnerstruktur aus den gewählten Kategorien, pro Kategorie eine Übersichtstabelle.
3. Nur Ordner und sprechende Dateinamen, keine Übersicht.

Für Google Drive:

a. Weiterhin nur über den synchronisierten Ordner der Drive-App.
b. Direkte Anmeldung mit Google (OAuth) und Zugriff über die Drive-Schnittstelle.

## Entscheidung

Die Ablage ist eine Ordnerstruktur aus den gewählten Kategorien mit einer Übersichtstabelle pro Kategorie (Option 2). Das Ziel ist wählbar: lokaler Ordner oder Google Drive mit direkter Anmeldung (Option b).

- Nutzer sehen ihre Ablage in einem Werkzeug, das sie kennen (Explorer, Finder, Drive), ohne zusätzliches Programm. Eine SQLite-Datei (Option 1) wäre für sie unsichtbar und in synchronisierten Ordnern anfällig für Beschädigung.
- Die Übersichtstabelle macht die ausgelesenen Angaben filter- und summierbar, was reine Ordner (Option 3) nicht leisten. In Google Drive ist sie eine Google-Tabelle, lokal eine CSV- bzw. Excel-Datei.
- Die direkte Anmeldung (Option b) erspart die Installation der Drive-App. PaperPilot fordert nur das engste Recht an (Zugriff auf selbst angelegte Dateien, Scope `drive.file`), nicht auf den Rest von Drive.

## Folgen

- Beide Ziele sind Adapter des Ports `StorageTarget` ([0002](0002-ports-und-adapter.md)) und bestehen denselben Vertragstest. Regel 3 (nie überschreiben, nie löschen) gilt für beide.
- Der Port bekommt eine Operation für Übersichtstabellen mit festen Spalten pro Kategorie. Heute erfüllen `tracker.csv` und `fristen.csv` diese Rolle über `read_text`/`write_text`.
- Der synchronisierte Drive-Ordner (Option a) bleibt als „lokaler Ordner“ möglich.
- Für die direkte Anmeldung muss PaperPilot bei Google als OAuth-App registriert werden. Ob dafür eine Prüfung durch Google nötig ist, wird vor dem Bau anhand der offiziellen Unterlagen geklärt. Das OAuth-Token wird wie andere Zugangsdaten im Schlüsselbund gespeichert ([0004](0004-zugangsdaten-im-schluesselbund.md)).
- Der Drive-Adapter importiert seine Abhängigkeiten erst in der Funktion und ist ein optionales Extra.
