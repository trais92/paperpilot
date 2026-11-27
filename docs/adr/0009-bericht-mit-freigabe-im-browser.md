# 0009: Bericht mit Freigabe als lokale Seite ohne JavaScript

- Status: Akzeptiert
- Datum: 2026-11-27
- Erster Baustein der Bedienung ohne Terminal (Roadmap 6)

## Kontext

Bisher entscheidet `--apply`, ob ein Lauf schreibt. Wer den Trockenlauf liest und eine falsche Kategorie entdeckt, kann sie nicht korrigieren, sondern nur die Regeln ändern oder den Lauf verwerfen. Für Menschen ohne Terminal-Erfahrung ist das zu umständlich. Gewünscht ist eine Seite im Browser, auf der man den Plan sieht, Kategorien korrigiert und den Lauf freigibt.

Randbedingungen: Kern ohne Abhängigkeiten (Regel 7), Trockenlauf bleibt Standard (Regel 4), Unsicheres bleibt `unklar` (Regel 5). Eine lokale Seite ist ein Angriffsziel: Jede andere Seite im selben Browser kann Anfragen an `127.0.0.1` schicken (CSRF), und Mails enthalten beliebigen, auch bösartigen Text (XSS).

## Optionen

1. Web-Framework (Flask, FastAPI) mit Vorlagen-Engine und JavaScript-Oberfläche.
2. `http.server` aus der Standardbibliothek, Seiten als HTML-Text mit einem Formular, kein JavaScript.
3. Desktop-Oberfläche (Tkinter, Qt).

## Entscheidung

**Option 2.** Die Seite braucht genau ein Formular: eine Auswahlliste pro Mail und zwei Knöpfe. Das geht ohne JavaScript und ohne Paket. Desktop-Oberflächen sehen auf jedem System anders aus und lassen sich schlecht testen.

- **Planen und Ausführen bleiben getrennt.** Die Seite zeigt den Plan aus dem Trockenlauf. Erst „Freigeben“ führt `pipeline.run(..., apply=True)` aus, mit einem `FixedClassifier`, der die gezeigten Kategorien samt Korrekturen zurückgibt. Die KI wird beim Ausführen nicht erneut gefragt, es landet also genau das, was der Mensch gesehen hat. Korrekturen tragen die Begründung „vom Menschen korrigiert“.
- **Nur gültige Kategorien.** Eine unbekannte Kategorie im Formular bricht die Freigabe ab, ohne zu schreiben. Eine Sitzung kann nur einmal freigegeben oder abgebrochen werden.
- **Logik ohne HTTP.** `ReviewSession` (Plan, Seite, Freigabe) ist reines Python und wird ohne Server getestet; `server.py` ist eine dünne Hülle.
- **Schutz der lokalen Seite:**
  - lauscht nur auf `127.0.0.1`, Port zufällig;
  - Zufallstoken (`secrets.token_urlsafe(32)`) in der Adresse, die PaperPilot selbst öffnet, und als verstecktes Feld in jedem Formular; ohne Token antwortet der Server mit 404;
  - Formulare mit fremdem `Origin` werden abgewiesen;
  - jeder Wert aus einer Mail geht durch `html.escape`;
  - Content-Security-Policy `default-src 'none'`: keine Skripte, keine fremden Quellen, Formulare nur an sich selbst, nicht einbettbar;
  - Adressen werden nicht protokolliert, weil sie das Token enthalten;
  - Post/Redirect/Get, damit Neuladen nicht erneut absendet.
- **Ende des Servers:** nach Freigabe oder Abbruch (sobald die Ergebnisseite geladen ist), nach 30 Minuten ohne Entscheidung oder mit Strg+C. Ohne Freigabe wird nichts geschrieben.

## Folgen

- `paperpilot run --browser` ersetzt für Menschen den Schalter `--apply`; `--apply` bleibt für zeitgesteuerte Läufe. Beide schließen sich aus.
- Der Einrichtungsassistent (Roadmap 8) kann denselben Server-Aufbau nutzen.
- Ohne JavaScript gibt es keine Live-Aktualisierung. Für einen Lauf mit wenigen Dutzend Mails reicht ein Formular.
- Korrigiert werden zunächst nur Kategorien. Felder wie Betrag und Frist kommen mit Roadmap 4 hinzu.
