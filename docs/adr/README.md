# Architekturentscheidungen (ADRs)

Jede Entscheidung, die die Struktur von PaperPilot prägt, steht hier als kurzes Dokument: Kontext, betrachtete Optionen, Entscheidung, Folgen. ADRs werden nicht nachträglich umgeschrieben. Ändert sich eine Entscheidung, entsteht ein neues ADR, und das alte bekommt den Status „Ersetzt durch …“.

| Nr. | Titel | Status | Umsetzung |
|---|---|---|---|
| [0001](0001-entscheidungen-als-adr.md) | Architekturentscheidungen als ADR festhalten | Akzeptiert | erledigt |
| [0002](0002-ports-und-adapter.md) | Kern mit Ports und Adaptern | Akzeptiert | erledigt |
| [0003](0003-ki-fest-eingebaut.md) | KI fest eingebaut, Regeln als Vorfilter | Akzeptiert | Einordnung erledigt (0007), Felder geplant |
| [0004](0004-zugangsdaten-im-schluesselbund.md) | Zugangsdaten im Schlüsselbund des Betriebssystems | Akzeptiert | erledigt |
| [0005](0005-ablage-ordnerstruktur-lokal-oder-drive.md) | Ablage als Ordnerstruktur, lokal oder in Google Drive | Akzeptiert | lokal erledigt, Drive geplant |
| [0006](0006-imap-als-einzige-mailquelle.md) | IMAP als einzige Quelle für echte Mails | Akzeptiert | erledigt |
| [0007](0007-ki-schicht-mit-austauschbaren-modellen.md) | KI-Schicht mit austauschbaren Sprachmodellen | Vorgeschlagen | erledigt |

## Vorlage

```markdown
# NNNN: Titel als Entscheidung formuliert

- Status: Vorgeschlagen | Akzeptiert | Ersetzt durch NNNN
- Datum: JJJJ-MM-TT

## Kontext
Welches Problem, welche Randbedingungen?

## Optionen
1. …
2. …

## Entscheidung
Was gilt ab jetzt, in einem Satz, danach die Begründung.

## Folgen
Was wird leichter, was schwerer, was ist zu beachten?
```
