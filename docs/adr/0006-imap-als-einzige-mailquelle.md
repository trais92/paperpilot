# 0006: IMAP als einzige Quelle für echte Mails

- Status: Akzeptiert
- Datum: 2026-11-26

## Kontext

Neben IMAP wäre ein Import exportierter Mails (`.eml`, `mbox`) ohne jede Anmeldung möglich, ebenso Anbieter-Schnittstellen wie die Gmail-API.

## Optionen

1. IMAP, strikt lesend.
2. Zusätzlich Datei-Import (`.eml`, `mbox`).
3. Anbieter-Schnittstellen (Gmail-API, Microsoft Graph).

## Entscheidung

Echte Mails kommen ausschließlich über IMAP (Option 1). `JsonSource` bleibt für Demo, Tests und Evaluation.

IMAP funktioniert mit praktisch jedem Anbieter, erlaubt automatische Läufe und braucht nur ein App-Passwort. Ein Datei-Import würde automatische Läufe ausschließen und einen zweiten Weg mit eigener Doku und eigenen Tests erzeugen. Anbieter-Schnittstellen bringen pro Anbieter eine OAuth-Einrichtung mit.

## Folgen

- Regel 2 gilt unverändert: Postfach nur lesend (`readonly`, `BODY.PEEK`), nie senden, verschieben, löschen oder als gelesen markieren.
- Der Einrichtungsassistent führt Anbieter-spezifisch zum App-Passwort (zuerst Gmail).
- Eine weitere Quelle bleibt über den Port `MailSource` möglich, ist aber nicht geplant.
