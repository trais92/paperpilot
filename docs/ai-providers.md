# KI-Anbieter

PaperPilot fragt für jede Mail, die nicht schon der Vorfilter als Werbung erkannt hat, ein Sprachmodell nach der passenden Kategorie. Welche Anbieter es gibt, was sie kosten und wie man sie einrichtet, steht hier. Die Architektur dahinter: [ADR 0007](adr/0007-ki-schicht-mit-austauschbaren-modellen.md).

## Überblick

| Anbieter | Rolle | Kosten | Modell (Standard) | Schnittstelle |
|---|---|---|---|---|
| Groq | voreingestellt | kostenloser Tarif mit Kontingent | `openai/gpt-oss-20b` | OpenAI-kompatibel, ohne Zusatzpaket |
| Mistral | Reserve | laut Doku nur mit aktivierter Abrechnung | `mistral-small-latest` | OpenAI-kompatibel, ohne Zusatzpaket |
| Claude (Anthropic) | optional | nutzungsabhängig | `claude-opus-5-5` | offizielles SDK, Extra `[llm]` |

Die Reihenfolge steht in der Konfiguration (`[ai]`, siehe [configuration.md](configuration.md#ai)). Anbieter ohne gespeicherten Schlüssel werden übersprungen. Fällt der erste Anbieter aus (keine Verbindung, Schlüssel abgelehnt, Kontingent erschöpft), wird der nächste gefragt. Antwortet keiner, landet die Mail als `unklar` im Eingang und wird beim nächsten Lauf erneut versucht.

## Einrichten

```bash
pip install ".[keyring]"
paperpilot login --ai groq        # Schlüssel einfügen, wird im Schlüsselbund gespeichert
paperpilot run                    # Trockenlauf mit KI
```

Ohne Schlüsselbund: Umgebungsvariable `PAPERPILOT_GROQ_API_KEY` (bzw. `PAPERPILOT_MISTRAL_API_KEY`, `PAPERPILOT_CLAUDE_API_KEY`).

- **Groq:** Konto auf console.groq.com anlegen, unter *API Keys* einen Schlüssel erzeugen.
- **Mistral:** Konto auf console.mistral.ai, Abrechnung aktivieren, Schlüssel erzeugen. Unter den Datenschutz-Einstellungen lässt sich die Nutzung der Daten zum Training abschalten.
- **Claude:** Konto auf platform.claude.com, Schlüssel erzeugen, `pip install ".[llm]"`.

## Was gesendet wird

Pro Mail ein Aufruf mit der Liste der erlaubten Kategorien samt Beschreibung, Absender, Betreff und höchstens 4000 Zeichen des Textes. Anhänge werden nicht gesendet. Werbung, die der Vorfilter erkennt, und Duplikate gehen gar nicht erst an die KI. Mehr dazu im [Sicherheitskonzept](security.md#ki-anbieter).

## Kontingente

Gratis-Tarife begrenzen Anfragen pro Minute und pro Tag. PaperPilot hält deshalb einen Mindestabstand zwischen zwei Anfragen (Groq 2 s, Mistral 1 s), wartet bei „zu viele Anfragen“ (HTTP 429) einmal so lange, wie der Anbieter mit `Retry-After` verlangt (höchstens 20 s), und fragt danach die Reserve.

## Stand der Angaben und Quellen

Geprüft am 27.11.2026 in den offiziellen Unterlagen. Anbieter ändern Tarife und Modellnamen; Modelle lassen sich deshalb in `[ai.models]` überschreiben, ohne den Code anzufassen.

- Mistral, Chat-Schnittstelle (Endpunkt, Anmeldung, `response_format` mit `json_object` und `json_schema`): https://docs.mistral.ai/api/endpoint/chat
- Mistral, Nutzung und Kontingente („Free mode … doesn't include API access“, API erst nach Aktivierung der Abrechnung): https://docs.mistral.ai/deployment/ai-studio/tier
- Groq, Schnittstelle (Endpunkt `https://api.groq.com/openai/v1/chat/completions`): https://console.groq.com/docs/api-reference
- Groq, strukturierte Ausgabe (JSON-Modus für alle Modelle, strenges Schema nur für einzelne): https://console.groq.com/docs/structured-outputs
- Groq, Kontingente des kostenlosen Tarifs und `retry-after`: https://console.groq.com/docs/rate-limits

**Noch nicht gegen die echten Schnittstellen gemessen.** Alle Tests laufen mit Attrappen. Beim ersten echten Lauf prüfen: Groq akzeptiert `response_format: json_object` mit `openai/gpt-oss-20b`; Claude akzeptiert `fallbacks="default"` mit der Beta `server-side-fallback-2026-07-01` in der installierten SDK-Version.
