# 0002: Kern mit Ports und Adaptern

- Status: Akzeptiert
- Datum: 2026-11-26

## Kontext

Bisher war der Kern (Planen, Ausführen, Bericht) direkt an das Dateisystem gebunden (`LocalStore`, Pfade über `store.root`), Zugangsdaten wurden in der CLI aus Umgebungsvariablen gelesen. Geplant sind mehrere austauschbare Techniken: verschiedene KI-Anbieter ([0003](0003-ki-fest-eingebaut.md)), Google Drive neben dem lokalen Ordner ([0005](0005-ablage-ordnerstruktur-lokal-oder-drive.md)) und der Schlüsselbund des Betriebssystems ([0004](0004-zugangsdaten-im-schluesselbund.md)). Jede davon direkt im Kern zu verdrahten, würde ihn mit Fallunterscheidungen und Netzwerkcode füllen und das Testen ohne Netz erschweren.

## Optionen

1. Fallunterscheidungen im Kern (`if target == "drive": …`).
2. Abstrakte Basisklassen mit Vererbung.
3. Ports als `typing.Protocol`, Adapter als eigenständige Klassen (strukturelle Typisierung).

## Entscheidung

Der Kern hängt nur von Ports in `src/paperpilot_ops/ports.py` ab (Option 3):

| Port | Aufgabe | Adapter |
|---|---|---|
| `MailSource` | Mails seit dem letzten Lauf liefern | `ImapSource`, `JsonSource` (Demo, Tests) |
| `Classifier` | Label oder `unklar` bestimmen | `RuleClassifier`, `LLMClassifier`; wird mit [0003](0003-ki-fest-eingebaut.md) zur KI-Analyse mit Feldern erweitert |
| `StorageTarget` | Ablegen ohne Überschreiben, Übersichten, Duplikat-Index, Lauf-Stand | `LocalStore`, `MemoryStore`; Google Drive geplant |
| `CredentialStore` | Zugangsdaten lesen | `EnvCredentialStore`; Schlüsselbund geplant |

Protokolle brauchen keine gemeinsame Basisklasse, ein Adapter muss nur die Methoden haben. `mypy --strict` prüft das in der CI. Vererbung (Option 2) würde Adapter an eine Klassenhierarchie binden, ohne zusätzlichen Nutzen.

## Folgen

- Jeder Port hat einen schriftlichen Vertrag im Docstring und einen Vertragstest. Für `StorageTarget` ist das `tests/test_storage_contract.py`: Ein neuer Adapter wird dort eingetragen und muss dieselben Tests bestehen wie `LocalStore`.
- Tests des Kerns laufen mit `MemoryStore` und Fake-Clients, ohne Dateisystem und ohne Netz.
- Tracker und Fristen werden über `read_text`/`write_text` des Ablageziels geschrieben, nicht mehr über Pfade. So funktionieren sie mit jedem Adapter.
- Adapter für externe Dienste importieren ihre Pakete erst in der Funktion. Der Kern bleibt ohne Laufzeit-Abhängigkeiten.
