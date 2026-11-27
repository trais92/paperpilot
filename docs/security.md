# Sicherheitskonzept

PaperPilot arbeitet mit dem Postfach, mit privaten Dokumenten und mit Zugangsdaten. Dieses Dokument beschreibt, was geschützt wird, gegen wen, und wo im Code das passiert. Jede Zusage hier ist durch einen Test abgesichert; die Spalte „Geprüft in“ nennt ihn.

## Schutzgüter

| Was | Warum schützenswert |
|---|---|
| Postfach | Darf nie verändert werden: keine Mail senden, verschieben, löschen oder als gelesen markieren |
| Zugangsdaten (App-Passwort, später KI-Schlüssel und Google-Token) | Voller Zugriff auf Postfach bzw. Konten |
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

## Meldung von Schwachstellen

Bitte nicht als öffentliches Issue, sondern über die private Sicherheitsmeldung von GitHub („Report a vulnerability“ im Reiter *Security* des Repositorys).
