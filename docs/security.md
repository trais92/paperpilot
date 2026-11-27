# Sicherheitskonzept

PaperPilot arbeitet mit dem Postfach, mit privaten Dokumenten und mit Zugangsdaten. Dieses Dokument beschreibt, was geschützt wird, gegen wen, und wo im Code das passiert. Jede Zusage hier ist durch einen Test abgesichert; die Spalte „Geprüft in“ nennt ihn.

## Schutzgüter

| Was | Warum schützenswert |
|---|---|
| Postfach | Darf nie verändert werden: keine Mail senden, verschieben, löschen oder als gelesen markieren |
| Zugangsdaten (App-Passwort, KI-Schlüssel, später Google-Token) | Voller Zugriff auf Postfach bzw. Konten |
| Abgelegte Dokumente | Private Inhalte; ein Überschreiben wäre Datenverlust |
| Mail-Inhalte unterwegs | Gehen nur an Dienste, die der Mensch ausgewählt hat |

## Grundsätze

1. **Nur lesen, wo gelesen wird.** IMAP mit `EXAMINE` (`select(readonly=True)`) und `BODY.PEEK[]`.
2. **Nie überschreiben, nie löschen.** Gilt für jedes Ablageziel, geprüft im Vertragstest.
3. **Erst planen, dann nach Freigabe ausführen.** Ohne `--apply` wird nichts geschrieben.
4. **Zugangsdaten nur im Schlüsselbund.** Siehe unten.
5. **Kein Paket ohne Not.** Der Kern hat keine Laufzeit-Abhängigkeiten; jedes Zusatzpaket ist ein optionales Extra und wird erst beim Gebrauch geladen.

## Zugangsdaten

Entscheidung und Alternativen: [ADR 0004](adr/0004-zugangsdaten-im-schluesselbund.md).

| Zusage | Umsetzung | Geprüft in |
|---|---|---|
| Dauerhaft nur im Schlüsselbund des Betriebssystems | `KeyringCredentialStore`, Dienstname `paperpilot` | `test_keyring_roundtrip_under_own_service_name` |
| `paperpilot login` legt keine Datei an | Werte gehen direkt in den Schlüsselbund | `test_login_stores_in_keyring_and_nowhere_else` |
| Werte erscheinen nie in Ausgaben | `login --status` zeigt nur „gespeichert“/„fehlt“ | `test_status_shows_presence_but_never_values` |
| Werte erscheinen nie in Fehlermeldungen | Fehler des Betriebssystems werden durch eine eigene Meldung ersetzt, ohne den Originaltext anzuhängen (`from None`) | `test_backend_errors_never_contain_the_secret`, `test_failed_check_stores_nothing` |
| Werte erscheinen nie in `repr()` | eigenes `__repr__` für alle Adapter und `ImapSource` | `test_repr_never_shows_values` |
| Falsche Zugangsdaten werden nicht gespeichert | Probe-Anmeldung vor dem Speichern | `test_failed_check_stores_nothing` |
| Nur bekannte Schlüssel | `KEYS`; alles andere ist `KeyError` | `test_unknown_key_is_a_programming_error` |
| Löschen ist jederzeit möglich | `paperpilot logout` | `test_logout_deletes_everything` |

Reihenfolge beim Lesen: erst Umgebungsvariablen, dann Schlüsselbund. So können Server und CI ohne Schlüsselbund arbeiten, und ein Mensch kann einen gespeicherten Wert für einen Lauf bewusst übersteuern. Was fehlt, fragt der Lauf ab und vergisst es danach wieder.

Grenzen: Wer am entsperrten Benutzerkonto sitzt, kann den Schlüsselbund lesen. Das ist bei jedem Programm so, das ohne Passwortabfrage laufen soll, und der Grund, warum PaperPilot nur ein App-Passwort verlangt, das sich beim Mailanbieter einzeln widerrufen lässt.

## KI-Anbieter

Entscheidungen: [ADR 0003](adr/0003-ki-fest-eingebaut.md), [ADR 0007](adr/0007-ki-schicht-mit-austauschbaren-modellen.md). Welche Anbieter, welche Datenregeln: [ai-providers.md](ai-providers.md).

| Zusage | Umsetzung | Geprüft in |
|---|---|---|
| Werbung geht nicht an die KI | Vorfilter vor jedem KI-Aufruf | `test_prefilter_keeps_advertising_away_from_ai` |
| Anhänge gehen nicht an die KI, Text höchstens 4000 Zeichen | `AIClassifier.prompt()` | `test_long_bodies_are_cut_and_attachments_never_sent` |
| Eine Mail kann der KI keine Kategorie aufzwingen, die es nicht gibt | Antwort muss ein Label aus der erlaubten Liste sein, sonst `unklar` | `test_invalid_answers_become_unclear` |
| Anweisungen in der Mail werden als Inhalt behandelt | Systemprompt sagt es ausdrücklich; die Begrenzer `<<<MAIL`/`MAIL>>>` werden aus dem Mailtext entfernt, damit sie sich nicht fälschen lassen | `test_prompt_lists_categories_with_descriptions_and_delimits_mail` |
| Ausfall heißt Mensch, nicht Raten | Jede Störung wird `unklar`; kein Rückfall auf die Regeln | `test_provider_failure_becomes_unclear_not_rules` |
| Dieselbe Mail geht nicht unnötig an einen zweiten Anbieter | Reserve nur bei Störung, nicht bei falscher Antwort | `test_fallback_does_not_ask_reserve_after_an_answer` |
| Schlüssel nie in Meldungen oder `repr()` | eigene Meldungen, `__repr__` ohne Schlüssel, auch für die HTTP-Anfrage | `test_contract_key_never_in_repr`, `test_openai_http_errors` |
| Nur verschlüsselte Verbindungen | `OpenAICompatibleModel` lehnt andere Adressen als `https://` ab | `test_openai_only_https` |

Grenze: Eine Mail kann die KI zu einer falschen, aber erlaubten Kategorie verleiten. Deshalb bleibt der Trockenlauf Standard und jede Ablage nachvollziehbar (Begründung im Bericht).

## Meldung von Schwachstellen

Bitte nicht als öffentliches Issue, sondern über die private Sicherheitsmeldung von GitHub („Report a vulnerability“ im Reiter *Security* des Repositorys).
