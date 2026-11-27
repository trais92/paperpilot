# 0011: Angaben aus Mail und PDF auslesen, einzeln prüfen, Scans an den Menschen

- Status: Akzeptiert
- Datum: 2026-11-27
- Ergänzt [0003](0003-ki-fest-eingebaut.md) und [0007](0007-ki-schicht-mit-austauschbaren-modellen.md): Text aus PDF-Anhängen geht jetzt mit an die KI

## Kontext

Bisher erkennt die KI nur die Kategorie. Für Rechnungen, Verträge und Bescheide zählen aber Betrag, Belegdatum, Rechnungs- oder Kundennummer und Frist, und die stehen oft nur im PDF-Anhang. Roadmap 4 verlangt: Die Angaben landen in der Übersicht, gescannte PDFs ohne Text gehen in den Eingang.

Randbedingungen: Kern ohne Abhängigkeiten (Regel 7), unsicher heißt leer bzw. `unklar` (Regel 5), so wenig Daten wie nötig verlassen den Rechner, der Duplikat-Index hängt am Inhalt der abgelegten Dateien.

## Optionen

1. Angaben mit regulären Ausdrücken aus dem Text holen.
2. Eine zweite KI-Anfrage nur für die Angaben.
3. Dieselbe Anfrage liefert Kategorie und Angaben, jede Angabe wird einzeln geprüft.

Für PDFs: (a) `pypdf` als optionales Extra, (b) externe Programme wie `pdftotext`, (c) Texterkennung (OCR) für Scans.

## Entscheidung

**Option 3 mit (a).**

- **Eine Anfrage pro Mail.** Die Antwort bekommt ein Objekt `fields` mit `amount`, `currency`, `document_date`, `reference`, `due_date`; `null` heißt „nicht eindeutig“. Eine zweite Anfrage würde das Gratis-Kontingent halbieren, reguläre Ausdrücke scheitern an der Vielfalt von Rechnungen.
- **Jede Angabe wird einzeln geprüft** (`fields.py`): Betrag als Zahl mit ISO-Währung, Daten als echtes Kalenderdatum zwischen 2000 und 2100, Nummer als ein Wort aus Buchstaben, Ziffern und `. / _ -` mit höchstens 40 Zeichen. Eine ungültige Angabe wird verworfen und in der Begründung genannt; die Kategorie bleibt davon unberührt. Dieselben Prüfungen gelten für Korrekturen im Browser.
- **PDF-Text** über das optionale Extra `[pdf]` (`pypdf`, reines Python, keine Systemprogramme). Höchstens 5 Seiten und 3000 Zeichen aller PDFs zusammen gehen mit an die KI, innerhalb der Begrenzer der Mail. `[ai] read_pdfs = false` schaltet das ab. Andere Anhänge (Bilder, Office-Dateien) werden weiterhin nicht gesendet.
- **Scans gehen an den Menschen.** Liefert ein PDF keinen Text (Scan, beschädigt, verschlüsselt), wird die Mail ohne KI-Anfrage `unklar` mit dem Grund „PDF ohne lesbaren Text“. OCR (c) wäre eine schwere Abhängigkeit und für Anfänger schwer zu installieren.
- **Angaben ändern keine abgelegte Datei.** Sie stehen in der Übersicht (Spalten `Betrag`, `Belegdatum`, `Nummer`, `Frist`) und im Bericht, nicht in der abgelegten Markdown-Datei. So bleibt deren Hash gleich, auch wenn die KI beim nächsten Lauf eine Angabe anders liest, und der Duplikat-Schutz hält.
- **Frist laut KI** kommt zusätzlich in den Kalender (`fristen.ics`), wenn der Text sie nicht schon enthält.

## Folgen

- Übersichten bekommen drei neue Spalten; bestehende Tabellen werden laut Vertrag (`merge_table`) hinten erweitert.
- Mehr Daten verlassen den Rechner (PDF-Text). Das ist in [ai-providers.md](../ai-providers.md) und im [Sicherheitskonzept](../security.md#ki-anbieter) beschrieben und abschaltbar.
- Ohne `pypdf` verhält sich PaperPilot wie vorher: Anhänge werden nicht gelesen, Scans also auch nicht erkannt.
- Wie gut die Angaben stimmen, misst erst das neue Testset (Roadmap 5).
