# Evaluation

PaperPilot misst seinen Klassifizierer auf einem gelabelten Testset, damit Regeländerungen oder ein Wechsel zum LLM auf Zahlen beruhen statt auf Eindruck.

```bash
paperpilot eval                              # Regeln, mitgeliefertes Testset
paperpilot eval --classifier llm             # LLM, gleiches Testset
paperpilot eval --testset meine_mails.jsonl  # eigenes Testset
paperpilot eval --min-accuracy 0.85          # Exit-Code 1 darunter (CI)
```

## Testset

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
- **Kein Nachoptimieren:** Die Fehler oben könnten mit ein paar Stichwörtern behoben werden. Das ist bewusst nicht passiert, sonst misst das Testset nur noch, ob die Regeln es auswendig kennen. Wer optimiert, sollte vorher ein separates Validierungsset abspalten.
- **Kleine Klassen:** Bei 3 bis 5 Beispielen pro Klasse ändert ein einzelner Fehler den Recall um 20 bis 33 Punkte.
- **Synthetische Daten:** Echte Mails sind länger, haben Signaturen, Zitate und HTML. Ein Testset aus echten, anonymisierten Mails ist der wichtigste nächste Schritt.

## Regeln und LLM vergleichen

Vorgehen für einen fairen Vergleich (siehe [roadmap.md](roadmap.md)):

1. Testset vergrößern (Ziel: ≥ 200 Mails, ≥ 10 pro Klasse), davon 30 % als nie angesehenes Holdout.
2. `paperpilot eval` und `paperpilot eval --classifier llm` auf dem Holdout laufen lassen.
3. Neben Genauigkeit auch Kosten pro Mail und Laufzeit festhalten.
4. Hybrid prüfen: Regeln zuerst, LLM nur für `unklar`. Das senkt Kosten und Übergabequote zugleich.
