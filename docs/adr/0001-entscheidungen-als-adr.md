# 0001: Architekturentscheidungen als ADR festhalten

- Status: Akzeptiert
- Datum: 2026-11-26

## Kontext

PaperPilot wächst von einer regelbasierten CLI zu einem Werkzeug mit KI-Analyse, wählbarem Ablageziel und Oberfläche im Browser. Mehrere Entscheidungen der Version 0.1.0 werden dabei bewusst geändert (zum Beispiel „Zugangsdaten nie speichern“). Ohne schriftliche Begründung ist später nicht nachvollziehbar, warum etwas so gebaut ist, und Entscheidungen werden versehentlich rückgängig gemacht.

## Optionen

1. Begründungen nur in Commit-Nachrichten und Pull Requests.
2. Ein Abschnitt „Designentscheidungen“ in `docs/architecture.md`.
3. Ein ADR pro Entscheidung in `docs/adr/`.

## Entscheidung

Jede strukturprägende Entscheidung bekommt ein ADR in `docs/adr/` (Option 3).

Commit-Nachrichten verteilen das Wissen über die Historie. Ein einzelner Abschnitt in der Architektur-Doku zeigt nur den aktuellen Stand und verliert die betrachteten Alternativen. ADRs sind kurz, einzeln verlinkbar und zeigen auch, was verworfen wurde.

## Folgen

- Ein Pull Request, der eine Architekturentscheidung trifft oder ändert, enthält das passende ADR.
- `docs/architecture.md` beschreibt den Ist-Zustand und verlinkt die ADRs für das Warum.
- Akzeptierte ADRs werden nicht umgeschrieben, sondern durch neue ersetzt.
