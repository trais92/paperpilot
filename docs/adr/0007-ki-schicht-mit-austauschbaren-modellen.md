# 0007: KI-Schicht mit austauschbaren Sprachmodellen

- Status: Akzeptiert
- Datum: 2026-11-27
- Ergänzt [0003](0003-ki-fest-eingebaut.md); ersetzt dort die Anbieterwahl (Mistral als Standard, Groq als Reserve)

## Kontext

[ADR 0003](0003-ki-fest-eingebaut.md) legt fest, dass eine KI jede Mail einordnet, die den Vorfilter passiert. Als Anbieter waren Mistral (Standard), Groq (Reserve) und Claude (Option) vorgesehen. Offen war, wie die Anbieter technisch eingebunden werden, wie man ihren Antworten vertraut und was bei Ausfällen passiert. Randbedingungen: Kern ohne Abhängigkeiten (Regel 7), Tests ohne Netz, kein stiller Rückfall auf die Regeln (Regel 5).

Bei der Prüfung der offiziellen Unterlagen am 27.11.2026 ergab sich: Mistral bietet API-Zugang nur mit aktivierter Abrechnung. Groq dokumentiert einen kostenlosen Tarif ohne Kreditkarte mit festen Kontingenten (30 Anfragen pro Minute, 1000 pro Tag für `openai/gpt-oss-20b`). Weitere Kandidaten (Cerebras, GitHub Models, OpenRouter, Gemini) erfüllen die Bedingung „kostenlos, ohne Zahlungsmittel, kein Training mit den Daten“ derzeit nicht. Quellen und Einzelergebnisse in [docs/ai-providers.md](../ai-providers.md).

## Optionen

Einbindung:

1. Je Anbieter das offizielle Python-Paket.
2. Ein gemeinsamer Adapter für OpenAI-kompatible Schnittstellen mit `urllib`, Claude über sein SDK.
3. Eine Vermittlungsbibliothek für viele Anbieter (z. B. LiteLLM).

Antwortformat:

a. Strenges JSON-Schema beim Anbieter, Antwort ungeprüft übernehmen.
b. JSON-Modus beim Anbieter, Antwort in PaperPilot streng prüfen.

## Entscheidung

- **Port `LanguageModel`** in `ports.py` mit einer Methode `complete_json(system, user, schema) -> Completion`. Jede Störung wird zu `ProviderError` mit einer Art (`network`, `auth`, `rate_limit`, `server`, `refusal`, `invalid_response`). Der Klassifizierer kennt nur diesen Port.
- **Option 2:** `OpenAICompatibleModel` spricht OpenAI-kompatible Anbieter (heute Groq) mit der Standardbibliothek an; der HTTP-Baustein ist eine austauschbare Funktion (`Transport`), damit Tests ohne Netz laufen. `AnthropicModel` nutzt das offizielle SDK als optionales Extra `[llm]`. Option 1 brächte für jeden Gratis-Anbieter ein Pflichtpaket, Option 3 eine große Abhängigkeit für einen einfachen HTTP-Aufruf.
- **Option b:** Den JSON-Modus bieten OpenAI-kompatible Anbieter breit an, strenge Schemata nur für einzelne Modelle und mit unterschiedlicher Schreibweise. PaperPilot prüft jede Antwort selbst: gültiges JSON-Objekt, Label aus der erlaubten Liste, Sicherheit zwischen 0 und 1. Bei Claude wird zusätzlich das Schema übergeben. Antworten unterhalb von `min_confidence` (Standard 0,6) werden `unklar`.
- **Reserve-Kette (`FallbackModel`):** Der nächste Anbieter wird nur bei `ProviderError` gefragt. Eine inhaltlich unbrauchbare Antwort führt zu `unklar`, nicht zur Reserve, damit dieselbe Mail nicht ein zweites Mal das Haus verlässt. Anbieter ohne gespeicherten Schlüssel werden übersprungen.
- **Vorfilter (`PrefilteredClassifier`):** Nur Kategorien mit `action = "ignore"` (Werbung) entscheiden die Regeln. Alles andere entscheidet die KI.
- **Nur kostenlose Anbieter werden voreingestellt (Entscheidung Kai, 27.11.2026).** Standard ist Groq, ohne Reserve. Mistral entfällt, weil es eine Abrechnung verlangt. Claude bleibt als ausdrückliche Option für Menschen mit eigenem, kostenpflichtigem Schlüssel, nie voreingestellt. Ein zweiter Gratis-Anbieter wird als Reserve aufgenommen, sobald einer die Bedingungen erfüllt.
- **Kompositionswurzel:** `composition.py` ist der einzige Ort, der Ports mit Adaptern verbindet.

## Folgen

- Ohne Reserve hängt die Verfügbarkeit an Groq. Fällt Groq aus oder ist das Tageskontingent erschöpft, landen Mails als `unklar` im Eingang und werden beim nächsten Lauf erneut versucht; es geht nichts verloren.
- Neue Anbieter mit OpenAI-kompatibler Schnittstelle sind ein Eintrag in `ai/providers.py`. Jeder Adapter besteht den Vertragstest in `tests/test_ai_models.py`.
- `paperpilot run` nutzt standardmäßig die KI und bricht vor dem Abruf ab, wenn kein Schlüssel hinterlegt ist. `--classifier rules` bleibt als Weg ohne KI und als Vergleichswert in `paperpilot eval`.
- Die Umgebungsvariable `PAPERPILOT_MODEL` entfällt; Modelle stehen in `[ai.models]`.
- Gegen die echten Schnittstellen ist noch nichts gemessen. Das erste echte `paperpilot eval --classifier ai` je Anbieter kommt mit Roadmap-Punkt 5; die Zahlen werden in `docs/evaluation.md` festgehalten.
- Datenschutz: Gesendet werden Absender, Betreff und höchstens 4000 Zeichen Text, keine Anhänge. Details in [docs/security.md](../security.md).
