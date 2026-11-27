# 0007: KI-Schicht mit austauschbaren Sprachmodellen

- Status: Vorgeschlagen
- Datum: 2026-11-27
- Ergänzt [0003](0003-ki-fest-eingebaut.md); ändert dort den Standard-Anbieter (siehe unten)

## Kontext

[ADR 0003](0003-ki-fest-eingebaut.md) legt fest, dass eine KI jede Mail einordnet, die den Vorfilter passiert, mit Mistral als Standard, Groq als Reserve und Claude als Option. Offen war, wie die Anbieter technisch eingebunden werden, wie man ihren Antworten vertraut und was bei Ausfällen passiert. Randbedingungen: Kern ohne Abhängigkeiten (Regel 7), Tests ohne Netz, kein stiller Rückfall auf die Regeln (Regel 5).

Bei der Prüfung der offiziellen Unterlagen am 27.11.2026 ergab sich außerdem: Mistral schreibt, der kostenlose Modus enthalte keinen API-Zugang; Schlüssel und API-Nutzung setzen eine aktivierte Abrechnung voraus. Groq dokumentiert einen kostenlosen Tarif mit festen Kontingenten (z. B. 30 Anfragen pro Minute und 1000 pro Tag für `openai/gpt-oss-20b`). Quellen in [docs/ai-providers.md](../ai-providers.md).

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
- **Option 2:** `OpenAICompatibleModel` spricht Mistral und Groq mit der Standardbibliothek an; der HTTP-Baustein ist eine austauschbare Funktion (`Transport`), damit Tests ohne Netz laufen. `AnthropicModel` nutzt das offizielle SDK als optionales Extra `[llm]`. Option 1 brächte zwei Pflichtpakete für Gratis-Anbieter, Option 3 eine große Abhängigkeit für zwei einfache HTTP-Aufrufe.
- **Option b:** Den JSON-Modus bieten beide OpenAI-kompatiblen Anbieter für alle Modelle an, strenge Schemata nur für einzelne Modelle und mit unterschiedlicher Schreibweise. PaperPilot prüft jede Antwort selbst: gültiges JSON-Objekt, Label aus der erlaubten Liste, Sicherheit zwischen 0 und 1. Bei Claude wird zusätzlich das Schema übergeben. Antworten unterhalb von `min_confidence` (Standard 0,6) werden `unklar`.
- **Reserve-Kette (`FallbackModel`):** Der nächste Anbieter wird nur bei `ProviderError` gefragt. Eine inhaltlich unbrauchbare Antwort führt zu `unklar`, nicht zur Reserve, damit dieselbe Mail nicht ein zweites Mal das Haus verlässt. Anbieter ohne gespeicherten Schlüssel werden übersprungen.
- **Vorfilter (`PrefilteredClassifier`):** Nur Kategorien mit `action = "ignore"` (Werbung) entscheiden die Regeln. Alles andere entscheidet die KI.
- **Standard-Anbieter: Groq, Reserve: Mistral.** Abweichend von 0003, weil Mistral laut eigener Doku ohne Abrechnung keinen API-Zugang bietet und die Zielgruppe ohne Kreditkarte starten können soll. Die Reihenfolge ist eine Zeile in `[ai]` und lässt sich ohne Codeänderung umstellen.
- **Kompositionswurzel:** `composition.py` ist der einzige Ort, der Ports mit Adaptern verbindet.

## Folgen

- Neue Anbieter mit OpenAI-kompatibler Schnittstelle sind ein Eintrag in `ai/providers.py`. Jeder Adapter besteht den Vertragstest in `tests/test_ai_models.py`.
- `paperpilot run` nutzt standardmäßig die KI und bricht vor dem Abruf ab, wenn kein Schlüssel hinterlegt ist. `--classifier rules` bleibt als Weg ohne KI und als Vergleichswert in `paperpilot eval`.
- Die Umgebungsvariable `PAPERPILOT_MODEL` entfällt; Modelle stehen in `[ai.models]`.
- Gegen die echten Schnittstellen ist noch nichts gemessen. Das erste echte `paperpilot eval --classifier ai` je Anbieter kommt mit Roadmap-Punkt 5; die Zahlen werden in `docs/evaluation.md` festgehalten.
- Datenschutz: Gesendet werden Absender, Betreff und höchstens 4000 Zeichen Text, keine Anhänge. Details in [docs/security.md](../security.md).
