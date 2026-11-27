# KI-Anbieter

PaperPilot fragt für jede Mail, die nicht schon der Vorfilter als Werbung erkannt hat, ein Sprachmodell nach der passenden Kategorie. Welche Anbieter es gibt, nach welchen Kriterien sie ausgewählt sind und wie man sie einrichtet, steht hier. Die Architektur dahinter: [ADR 0007](adr/0007-ki-schicht-mit-austauschbaren-modellen.md).

## Auswahlkriterium

Voreingestellt wird nur, was **ohne Kreditkarte und ohne Abrechnung** dauerhaft nutzbar ist. PaperPilot richtet sich an Menschen ohne Programmierkenntnisse; ein Bezahlschritt bei der Einrichtung macht das Werkzeug für sie unbrauchbar. Zweites Kriterium ist der Datenschutz: Der Anbieter soll Mail-Inhalte nicht zum Training nutzen.

## Überblick

| Anbieter | Rolle | Kosten | Modell (Standard) | Schnittstelle |
|---|---|---|---|---|
| Groq | voreingestellt | kostenloser Tarif mit Kontingent, keine Kreditkarte | `openai/gpt-oss-20b` | OpenAI-kompatibel, ohne Zusatzpaket |
| Claude (Anthropic) | optional | kostenpflichtig, eigener Schlüssel | `claude-opus-5-5` | offizielles SDK, Extra `[llm]` |

Die Reihenfolge steht in der Konfiguration (`[ai]`, siehe [configuration.md](configuration.md#ai)). Wer einen Claude-Schlüssel hat, kann ihn mit `fallback = ["claude"]` als Reserve eintragen. Anbieter ohne gespeicherten Schlüssel werden übersprungen. Antwortet kein Anbieter, landet die Mail als `unklar` im Eingang und wird beim nächsten Lauf erneut versucht.

## Geprüfte, aber nicht aufgenommene Anbieter

Stand 27.11.2026, jeweils in den offiziellen Unterlagen geprüft:

| Anbieter | Ergebnis | Grund |
|---|---|---|
| Mistral | nicht aufgenommen | „Free mode … doesn't include API access“; API erst nach Aktivierung der Abrechnung |
| Cerebras | nicht aufgenommen | Testguthaben nur nach Hinterlegen eines Zahlungsmittels, verfällt nach 30 Tagen |
| GitHub Models | nicht aufgenommen | seit 30.07.2026 eingestellt |
| OpenRouter (`:free`-Modelle) | vorgemerkt, nicht aufgenommen | ohne Guthaben nur 50 Anfragen pro Tag; ob die Gratis-Endpunkte Daten zum Training nutzen, hängt vom jeweiligen Betreiber ab und ist nicht zugesichert |
| Google Gemini | nicht aufgenommen | im Gratis-Tarif Nutzung zum Training und menschliche Prüfung; für Angebote an Nutzer in der EU verlangen die Bedingungen den Bezahltarif |

Ein zweiter Gratis-Anbieter als Reserve kommt dazu, sobald einer beide Kriterien erfüllt. Die Schicht ist dafür vorbereitet: Ein OpenAI-kompatibler Anbieter ist ein Eintrag in `ai/providers.py`.

## Einrichten

```bash
pip install ".[keyring]"
paperpilot login --ai groq        # Schlüssel einfügen, wird im Schlüsselbund gespeichert
paperpilot run                    # Trockenlauf mit KI
```

Ohne Schlüsselbund: Umgebungsvariable `PAPERPILOT_GROQ_API_KEY` (bzw. `PAPERPILOT_CLAUDE_API_KEY`).

- **Groq:** Konto auf console.groq.com anlegen, unter *API Keys* einen Schlüssel erzeugen. Keine Kreditkarte nötig.
- **Claude (optional):** Konto auf platform.claude.com, Schlüssel erzeugen, `pip install ".[llm]"`, `paperpilot login --ai claude`.

## Was gesendet wird

Pro Mail ein Aufruf mit der Liste der erlaubten Kategorien samt Beschreibung, Absender, Betreff, höchstens 4000 Zeichen des Textes und, falls `pypdf` installiert ist (`pip install ".[pdf]"`), der Text von PDF-Anhängen (höchstens 5 Seiten, 3000 Zeichen zusammen). Andere Anhänge werden nie gesendet, und `[ai] read_pdfs = false` lässt auch PDFs auf dem Rechner. Ein PDF ohne lesbaren Text (Scan) geht nicht an die KI, sondern in den Eingang ([ADR 0011](adr/0011-angaben-aus-mail-und-pdf.md)). Werbung, die der Vorfilter erkennt, und Duplikate gehen gar nicht erst an die KI. Mehr dazu im [Sicherheitskonzept](security.md#ki-anbieter).

## Kontingente

Der kostenlose Groq-Tarif erlaubt für `openai/gpt-oss-20b` 30 Anfragen pro Minute und 1000 pro Tag. PaperPilot hält deshalb mindestens 2 Sekunden Abstand zwischen zwei Anfragen, wartet bei „zu viele Anfragen“ (HTTP 429) einmal so lange, wie der Anbieter mit `Retry-After` verlangt (höchstens 20 s), und fragt danach die Reserve, falls eine eingetragen ist. Bei 1000 Anfragen pro Tag reicht der Tarif für die allermeisten privaten Postfächer, zumal Werbung und Duplikate nicht mitzählen.

## Quellen

Anbieter ändern Tarife und Modellnamen; Modelle lassen sich deshalb in `[ai.models]` überschreiben, ohne den Code anzufassen.

- Groq, Schnittstelle (Endpunkt `https://api.groq.com/openai/v1/chat/completions`): https://console.groq.com/docs/api-reference
- Groq, strukturierte Ausgabe (JSON-Modus für alle Modelle, strenges Schema nur für einzelne): https://console.groq.com/docs/structured-outputs
- Groq, Kontingente des kostenlosen Tarifs und `retry-after`: https://console.groq.com/docs/rate-limits
- Mistral, Nutzung und Kontingente: https://docs.mistral.ai/deployment/ai-studio/tier
- Cerebras, Kontingente und Testguthaben: https://inference-docs.cerebras.ai/support/rate-limits
- GitHub Models, Einstellung: https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models
- OpenRouter, Kontingente der `:free`-Modelle: https://openrouter.ai/docs/api/reference/limits
- OpenRouter, Datenschutz: https://openrouter.ai/docs/faq

**Noch nicht gegen die echten Schnittstellen gemessen.** Alle Tests laufen mit Attrappen. Beim ersten echten Lauf prüfen: Groq akzeptiert `response_format: json_object` mit `openai/gpt-oss-20b`; Claude akzeptiert `fallbacks="default"` mit der Beta `server-side-fallback-2026-07-01` in der installierten SDK-Version.
