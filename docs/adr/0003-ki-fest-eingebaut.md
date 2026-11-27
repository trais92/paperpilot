# 0003: KI fest eingebaut, Regeln als Vorfilter

- Status: Akzeptiert
- Datum: 2026-11-26

## Kontext

Version 0.1.0 sortiert mit Stichwort-Regeln (90,4 % Label-Genauigkeit auf 52 Testmails), ein KI-Klassifizierer ist optional. Die Regeln stoßen an Grenzen: Flexion und Umlaute, indirekte Formulierungen, und sie können keine Angaben auslesen (Betrag, Fälligkeit, Kündigungsfrist). Eigene Kategorien, die Nutzer in einem Satz beschreiben, lassen sich mit Stichwörtern gar nicht abbilden. Die Zielgruppe sind Menschen ohne Programmierkenntnisse; sie sollen keine Stichwortlisten pflegen.

## Optionen

1. Regeln bleiben Standard, KI optional (Stand 0.1.0).
2. Hybrid: Regeln zuerst, KI nur bei `unklar`.
3. KI fest eingebaut für Kategorie und Felder, Regeln nur als Vorfilter.
4. Lokale Modelle (z. B. über Ollama).

## Entscheidung

Die KI analysiert jede Mail, die den Vorfilter passiert, und liefert Kategorie, Sicherheit, Begründung und die Felder der Kategorie (Option 3).

- **Standard-Anbieter:** Mistral (kostenloser Tarif ohne Kreditkarte, Anbieter mit Sitz in der EU).
- **Reserve:** Groq, wenn Mistral nicht antwortet oder das Kontingent erschöpft ist.
- **Optional:** Claude über die API mit eigenem Schlüssel.
- **Vorfilter:** Regeln sortieren Werbung, Newsletter und Duplikate aus, bevor etwas an die KI geht. Das spart Kontingent und schickt weniger private Inhalte nach außen.
- Mistral und Groq werden über eine gemeinsame, OpenAI-kompatible HTTP-Schnittstelle mit der Standardbibliothek angesprochen, ohne Zusatzpaket.

Lokale Modelle (Option 4) setzen passende Hardware und Einrichtung voraus und passen nicht zur Zielgruppe. Der Hybrid (Option 2) löst das Problem der fehlenden Felder und eigenen Kategorien nicht.

## Folgen

- Regel 5 gilt unverändert: Unbekannte Kategorie, ungültige Antwort, Ablehnung oder keine Verbindung ergeben `unklar`. Die Mail bleibt im Eingang und wird beim nächsten Lauf erneut versucht. Es gibt keinen stillen Rückfall auf die Regeln.
- Die Antwort der KI wird gegen die erlaubten Kategorien und Feldtypen geprüft, auch wenn der Anbieter strukturierte Ausgabe verspricht.
- `paperpilot eval` misst künftig Kategorie und Felder je Anbieter. Die Regeln bleiben als Vergleichswert erhalten. Ein Anbieter wird erst empfohlen, wenn seine Werte dokumentiert sind.
- Datenschutz: Jede Mail nach dem Vorfilter geht an den gewählten Anbieter. Der Einrichtungsassistent weist darauf hin und führt zur Einstellung, mit der Mistral die Daten nicht zum Training nutzt.
- Kontingente und Datenregeln der Gratis-Tarife werden vor dem Einbau in den offiziellen Unterlagen geprüft und in `docs/` festgehalten.
- Die Roadmap-Punkte „Hybrid-Klassifizierer“ und „Stichwort-Normalisierung“ entfallen.
