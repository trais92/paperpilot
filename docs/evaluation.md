# Evaluation

PaperPilot misst seinen Klassifizierer auf gelabelten Testsets, damit Regeländerungen und die Wahl des KI-Anbieters auf Zahlen beruhen statt auf Eindruck.

```bash
paperpilot eval                                          # Regeln, Standard-Testset (52 Mails, CI-Tor)
paperpilot eval --testset angaben --split dev            # Testset mit Angaben, nur Entwicklungsteil
paperpilot eval --testset angaben --split holdout        # nur der nie angesehene Teil
paperpilot eval --classifier ai --provider groq --testset angaben --json > groq.json
paperpilot eval --testset meine_mails.jsonl              # eigenes Testset
paperpilot eval --min-accuracy 0.85                      # Exit-Code 1 darunter (CI)
```

`--json` schreibt alle Kennzahlen (inkl. Verwechslungsmatrix) maschinenlesbar auf die Standardausgabe; Hinweise gehen dann auf die Fehlerausgabe. `--provider` misst einen Anbieter allein, ohne Reserve.

## Standard-Testset

[`src/paperpilot_ops/data/eval_set.jsonl`](../src/paperpilot_ops/data/eval_set.jsonl): 52 frei erfundene deutsche Mails, eine pro Zeile:

```json
{"id": "e06", "date": "2026-11-20T10:00", "from": "Recruiting <jobs@alpenblick-it.example>",
 "subject": "Einladung zum Vorstellungsgespräch", "body": "…", "label": "bewerbung/einladung"}
```

| Gruppe | Klassen | Mails |
|---|---|---|
| Bewerbung | eingangsbestaetigung, einladung, rueckfrage, absage, angebot | 22 |
| Privat | rechnungen, versicherungen, vertraege, steuern, wohnen, finanzen | 20 |
| Werbung | werbung (inkl. Job-Alerts) | 7 |
| Unklar | private Nachrichten, Vereinspost | 3 |

Bewusst enthalten sind schwierige Fälle: Job-Alerts mit Bewerbungswörtern, Absagen ohne „leider“, Rückfragen ohne das Wort „Bewerbung“ im Text, Abrechnungen, die nach Rechnung klingen.

## Metriken

| Metrik | Bedeutung |
|---|---|
| Genauigkeit (Label) | Anteil exakt richtiger Labels |
| Genauigkeit (Gruppe) | Anteil richtiger Gruppe (`bewerbung` / `privat` / `werbung` / `unklar`) |
| Precision pro Label | Wie oft stimmt das Label, wenn es vergeben wird? Wichtig für `werbung` (sonst gehen echte Mails verloren) |
| Recall pro Label | Wie viele echte Fälle werden gefunden? Wichtig für Einladungen und Angebote |
| Macro-F1 | Mittel der F1-Werte aller Klassen, jede Klasse zählt gleich |
| Übergabequote | Anteil `unklar`, also Arbeit, die beim Menschen landet |

## Ergebnis (Regeln, Stand v0.1.0)

| Kennzahl | Wert |
|---|---|
| Genauigkeit (Label) | 90,4 % |
| Genauigkeit (Gruppe) | 94,2 % |
| Macro-F1 | 0,905 |
| Übergabequote | 11,5 % |

| Label | Precision | Recall | n |
|---|---|---|---|
| bewerbung/absage | 1,00 | 0,60 | 5 |
| bewerbung/angebot | 1,00 | 1,00 | 3 |
| bewerbung/eingangsbestaetigung | 1,00 | 1,00 | 5 |
| bewerbung/einladung | 1,00 | 1,00 | 5 |
| bewerbung/rueckfrage | 1,00 | 0,75 | 4 |
| privat/finanzen | 1,00 | 0,67 | 3 |
| privat/rechnungen | 0,80 | 1,00 | 4 |
| privat/steuern | 1,00 | 1,00 | 3 |
| privat/versicherungen | 1,00 | 1,00 | 4 |
| privat/vertraege | 1,00 | 1,00 | 3 |
| privat/wohnen | 1,00 | 0,67 | 3 |
| unklar | 0,50 | 1,00 | 3 |
| werbung | 1,00 | 1,00 | 7 |

## Fehleranalyse

| ID | Erwartet | Ergebnis | Ursache |
|---|---|---|---|
| e11 | bewerbung/rueckfrage | unklar | „zu Ihrer Bewerbung“ trifft kein Gruppen-Stichwort („ihre bewerbung“ ≠ „ihrer bewerbung“) |
| e18 | bewerbung/absage | unklar | „zu deiner Bewerbung“ trifft das Gruppen-Stichwort „deine bewerbung“ nicht, daher zählt auch „leider“ nicht |
| e19 | bewerbung/absage | bewerbung/sonstiges | „Stelle wurde besetzt“ ist kein Absage-Stichwort, landet aber im richtigen Firmenordner |
| e44 | privat/wohnen | unklar | „Zählerstände“ enthält „zählerstand“ nicht (ä statt a), nur „wohnung“ im Text trifft: Score 1 < 2 |
| e48 | privat/finanzen | privat/rechnungen | „Kreditkartenabrechnung“ enthält sowohl „kreditkarte“ als auch „rechnung“, Gleichstand 2:2 |

Muster: Drei der fünf Fehler (e11, e18, e44) gehen auf reine Teilstring-Suche zurück (Flexion wie „ihrer“, Umlaut im Plural). Eine Normalisierung (Wortstämme, Umlaut-Varianten) wäre die naheliegende Verbesserung und steht in der [Roadmap](roadmap.md). Insgesamt sind die Regeln präzise (Precision fast überall 1,0), verlieren aber Recall bei indirekten Formulierungen. Die meisten Fehler sind `unklar`, also sicher, weil ein Mensch sie sieht.

## Grenzen und Fallstricke

- **Gleicher Autor:** Regeln und Testset stammen aus derselben Hand. Das begünstigt die Regeln. Die Zahlen sind eine Obergrenze, keine Prognose.
- **Kein Nachoptimieren:** Die Fehler oben könnten mit ein paar Stichwörtern behoben werden. Das ist bewusst nicht passiert, sonst misst das Testset nur noch, ob die Regeln es auswendig kennen. Für Optimierung gibt es jetzt das Testset mit Angaben und seinem `dev`-Teil.
- **Kleine Klassen:** Bei 3 bis 5 Beispielen pro Klasse ändert ein einzelner Fehler den Recall um 20 bis 33 Punkte.
- **Synthetische Daten:** Echte Mails sind länger, haben Signaturen, Zitate und HTML. Ein Testset aus echten, anonymisierten Mails ist der wichtigste nächste Schritt.

## Testset mit Angaben (Roadmap 5)

[`src/paperpilot_ops/data/testset.jsonl`](../src/paperpilot_ops/data/testset.jsonl): 208 erfundene Mails, 16 je Klasse, erzeugt von [`tools/make_testset.py`](../tools/make_testset.py) aus 40 Vorlagen mit festem Zufallsstartwert. Zusätzlich zu `label` enthält jede Mail:

- `fields`: erwartete Angaben (`amount`, `document_date`, `reference`, `due_date`), nur wenn sie wirklich im Text oder PDF stehen;
- `split`: `dev` (144) oder `holdout` (64). Jede dritte Vorlage einer Klasse liegt komplett im Holdout, damit es Formulierungen prüft, die beim Entwickeln nie zu sehen waren;
- bei 28 Mails ein PDF-Anhang, darunter 4 Scans ohne Text, die laut [ADR 0011](adr/0011-angaben-aus-mail-und-pdf.md) `unklar` ergeben müssen.

Ein Test stellt sicher, dass die Datei genau dem Generator entspricht (`python tools/make_testset.py --check`).

| Angabe | Precision | Recall |
|---|---|---|
| Bedeutung | Wie oft stimmt eine ausgegebene Angabe? | Wie viele erwartete Angaben werden gefunden? |

Verglichen wird exakt nach Normalisierung (`49,90 €` = `49.90 EUR`, Daten als `JJJJ-MM-TT`). Eine erfundene Angabe senkt die Precision, eine verpasste den Recall.

### Ergebnisse

| Klassifizierer | Split | Mails | Label | Gruppe | Macro-F1 | an Mensch | Angaben |
|---|---|---|---|---|---|---|---|
| Regeln | dev | 144 | 76,4 % | 83,3 % | 0,782 | 21,5 % | liest keine aus |
| Regeln | holdout | 64 | 39,1 % | 46,9 % | 0,300 | 60,9 % | liest keine aus |
| KI (Groq) | dev / holdout | | noch nicht gemessen | | | | |
| KI (Claude) | dev / holdout | | noch nicht gemessen | | | | |

Die Lücke zwischen dev und holdout zeigt die Schwäche der Stichwörter: Bei neuen Formulierungen findet der Regel-Klassifizierer die Kategorie meist nicht und gibt ab (`unklar`), statt falsch abzulegen. Genau dafür ist die KI fest eingebaut ([ADR 0003](adr/0003-ki-fest-eingebaut.md)); die Regeln bleiben Vorfilter für Werbung, wo sie auch im Holdout fehlerfrei sind.

Die KI-Zeilen brauchen einen echten Schlüssel und laufen deshalb nicht in der CI. Messen mit:

```bash
paperpilot login --ai groq
paperpilot eval --classifier ai --provider groq --testset angaben --split holdout --json > groq-holdout.json
```

Bei 208 Mails und mindestens 2 Sekunden Abstand dauert ein Lauf gut sieben Minuten und bleibt im Gratis-Kontingent von Groq (1000 Anfragen am Tag).

## Regeln und KI vergleichen

1. Nur auf `dev` entwickeln und nachjustieren (Beschreibungen der Kategorien, Prompt).
2. Erst am Ende einmal auf `holdout` messen und die Zahlen hier eintragen, mit Datum und Modell.
3. Neben Genauigkeit die Übergabequote und die Precision der Angaben beachten: Eine falsche Frist ist schlimmer als eine fehlende.
