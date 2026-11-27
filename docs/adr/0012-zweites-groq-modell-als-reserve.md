# 0012: Zweites Groq-Modell als Reserve mit demselben Schlüssel

- Status: Akzeptiert
- Datum: 2026-11-27
- Ergänzt [0007](0007-ki-schicht-mit-austauschbaren-modellen.md): Die Reserve-Kette kann innerhalb eines Anbieters weitere Modelle enthalten

## Kontext

Voreingestellt werden nur Anbieter ohne Kreditkarte und ohne Abrechnung ([ai-providers.md](../ai-providers.md#auswahlkriterium)). Diese Kriterien erfüllt derzeit nur Groq. Ein zweiter Gratis-Anbieter als Reserve fehlt also; ist das Tageskontingent von `openai/gpt-oss-20b` (1000 Anfragen) aufgebraucht, landen alle weiteren Mails als `unklar` im Eingang.

Groq führt die Kontingente in seiner Übersicht je Modell. Ein zweites Modell desselben Anbieters hat also eine eigene Zeile mit eigenem Tageskontingent. Ausdrücklich zugesichert ist die Trennung in den Unterlagen nicht; sie sagen nur, dass die Grenzen für die ganze Organisation gelten, nicht je Person.

## Optionen

1. Nichts ändern und warten, bis ein zweiter Gratis-Anbieter die Kriterien erfüllt.
2. Ein zweites Groq-Modell mit demselben Schlüssel als Reserve hinter das erste stellen.
3. Die Modelle abwechselnd fragen (Lastverteilung).

## Entscheidung

**Option 2.** `OpenAICompatibleProvider` bekommt ein optionales `reserve_model`; für Groq ist es `openai/gpt-oss-120b`, ein Produktionsmodell aus derselben Familie mit derselben Antwortform. `build_language_model()` stellt es als eigenes `OpenAICompatibleModel` mit dem Namen `groq-reserve` direkt hinter das erste Modell, noch vor Reserve-Anbieter aus `fallback`. Es gilt der bestehende Vertrag von `FallbackModel`: Gefragt wird nur bei `ProviderError` (Kontingent erschöpft, Dienst gestört, keine Verbindung), nie wegen einer inhaltlich unbrauchbaren Antwort.

- Kein neuer Schlüssel, keine neue Einwilligung: Die Mail geht an denselben Anbieter wie vorher.
- Abschaltbar mit `[ai] reserve_models = false`. Wer in `[ai.models]` schon das Reservemodell als Hauptmodell einträgt, bekommt es nicht doppelt.
- Welches Modell geantwortet hat, steht wie bisher in der Begründung (`groq-reserve`).

Option 3 hätte das stärkere Modell bei jeder zweiten Mail gefragt und die Ergebnisse schwerer vergleichbar gemacht; die Evaluation misst das Hauptmodell.

## Folgen

- Das kostenlose Tageskontingent reicht etwa doppelt so weit, sofern Groq die Modelle weiter getrennt zählt. Trifft das nicht mehr zu, kostet die Reserve nur eine zusätzliche, abgelehnte Anfrage.
- Ist das erste Modell gestört oder lehnt den Schlüssel ab, wird das zweite einmal gefragt. Bei abgelehntem Schlüssel scheitert es genauso; die Mail wird `unklar`.
- Das Reservemodell ist wie die übrigen KI-Adapter noch nicht gegen die echte Schnittstelle geprüft und wird in der Evaluation nicht eigens gemessen.
