"""Kommandozeile: paperpilot demo | run | eval | init | login | logout"""

from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path

from . import __version__
from .classify import make_classifier
from .config import default_rules_text, load_rules
from .credentials import KEYS, CredentialStoreError, KeyringCredentialStore, default_credential_store
from .evaluate import evaluate, render_eval
from .pipeline import render_report, run
from .ports import CredentialStore, MailSource, MutableCredentialStore
from .sources import ImapSource, JsonSource
from .store import LocalStore


def _data(name: str) -> Path:
    return Path(str(resources.files("paperpilot_ops").joinpath("data", name)))


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if args.reset and out.exists():
        shutil.rmtree(out)
    rules = load_rules(args.rules)
    store = LocalStore(out)
    mails = list(JsonSource(_data("demo_inbox.json")).fetch(store.last_run()))
    result = run(mails, make_classifier("rules", rules), rules, store, apply=True)
    print(render_report(result, store.location))
    print("\nTipp: 'paperpilot demo' nochmal ausführen zeigt die Idempotenz (0 neue Mails).")
    print("      'paperpilot eval' misst die Trefferquote auf dem Testset.")
    return 0


DEFAULT_IMAP_HOST = "imap.gmail.com"


def _imap_source(creds: CredentialStore) -> ImapSource:
    """IMAP-Quelle aus gespeicherten Zugangsdaten. Fehlende Werte werden abgefragt und nicht gespeichert."""
    host = creds.get("imap_host") or DEFAULT_IMAP_HOST
    user = creds.get("imap_user") or input("IMAP-Benutzer: ")
    password = creds.get("imap_password")
    if not password:
        print("Tipp: 'paperpilot login' speichert die Zugangsdaten im Schlüsselbund, dann entfällt die Abfrage.")
        password = getpass.getpass("App-Passwort (wird nicht gespeichert): ")
    return ImapSource(host, user, password)


def _open_vault() -> MutableCredentialStore:
    """Schlüsselbund des Betriebssystems. Eigene Funktion, damit Tests eine Attrappe einsetzen können."""
    return KeyringCredentialStore()


def _verify_imap(source: ImapSource) -> None:
    """Probe-Anmeldung vor dem Speichern. Eigene Funktion, damit Tests ohne Netz auskommen."""
    source.check()


def cmd_login(args: argparse.Namespace) -> int:
    """Zugangsdaten einmal abfragen und im Schlüsselbund speichern (docs/adr/0004)."""
    try:
        vault = _open_vault()
        if args.status:
            for key in KEYS:
                print(f"{key:<16} {'gespeichert' if vault.get(key) else 'fehlt'}")
            return 0
        host = input(f"IMAP-Server [{vault.get('imap_host') or DEFAULT_IMAP_HOST}]: ").strip()
        host = host or vault.get("imap_host") or DEFAULT_IMAP_HOST
        user = input("IMAP-Benutzer (Mailadresse): ").strip()
        password = getpass.getpass("App-Passwort: ")
        if not user or not password:
            print("Benutzer und App-Passwort sind Pflicht. Nichts gespeichert.", file=sys.stderr)
            return 1
        if not args.no_check:
            try:
                _verify_imap(ImapSource(host, user, password))
            except Exception as exc:  # Meldung des Servers kann Eingaben spiegeln, deshalb nur der Typ
                reason = type(exc).__name__
                print(f"Anmeldung bei {host} fehlgeschlagen ({reason}). Nichts gespeichert.", file=sys.stderr)
                return 1
        vault.set("imap_host", host)
        vault.set("imap_user", user)
        vault.set("imap_password", password)
    except CredentialStoreError as exc:
        print(f"{exc}\nAlternative ohne Schlüsselbund: Umgebungsvariablen, siehe README.", file=sys.stderr)
        return 2
    print(f"Gespeichert im Schlüsselbund ({host}, {user}). Löschen mit 'paperpilot logout'.")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    """Alle Einträge von PaperPilot aus dem Schlüsselbund löschen."""
    try:
        vault = _open_vault()
        removed = [key for key in KEYS if vault.delete(key)]
    except CredentialStoreError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Gelöscht: {', '.join(removed)}." if removed else "Im Schlüsselbund war nichts gespeichert.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    store = LocalStore(args.target or rules.target_dir)
    since = datetime.fromisoformat(args.since) if args.since else store.last_run()
    source: MailSource
    if args.source == "imap":
        source = _imap_source(default_credential_store())
    else:
        source = JsonSource(args.input or _data("demo_inbox.json"))
    mails = list(source.fetch(since))
    result = run(mails, make_classifier(args.classifier, rules), rules, store, apply=args.apply)
    print(render_report(result, store.location))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    samples = JsonSource(args.testset or _data("eval_set.jsonl")).load()
    report = evaluate(make_classifier(args.classifier, rules), samples)
    print(render_eval(report))
    if args.min_accuracy is not None and report.accuracy < args.min_accuracy:
        print(f"\nFEHLER: Genauigkeit {report.accuracy:.1%} < Mindestwert {args.min_accuracy:.1%}", file=sys.stderr)
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists():
        print(f"{path} existiert schon, nichts überschrieben.", file=sys.stderr)
        return 1
    path.write_text(default_rules_text(), "utf-8")
    print(f"Regeldatei angelegt: {path}. Anpassen und mit --rules {path} verwenden.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paperpilot", description="PaperPilot: Mails regelbasiert einsortieren.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="Komplettlauf auf anonymen Beispielmails")
    d.add_argument("--out", default="demo-ablage")
    d.add_argument("--reset", action="store_true", help="Demo-Ordner vorher leeren")
    d.add_argument("--rules")
    d.set_defaults(func=cmd_demo)

    r = sub.add_parser("run", help="Postfach einsortieren (Standard: Trockenlauf)")
    r.add_argument("--source", choices=["json", "imap"], default="json")
    r.add_argument("--input", help="JSON/JSONL-Datei bei --source json")
    r.add_argument("--rules")
    r.add_argument("--target", help="Ablage-Ordner (überschreibt target_dir)")
    r.add_argument("--classifier", choices=["rules", "llm"], default="rules")
    r.add_argument("--since", help="ISO-Datum, sonst seit letztem Lauf")
    r.add_argument("--apply", action="store_true", help="Plan wirklich ausführen")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("eval", help="Trefferquote auf gelabeltem Testset messen")
    e.add_argument("--testset")
    e.add_argument("--rules")
    e.add_argument("--classifier", choices=["rules", "llm"], default="rules")
    e.add_argument("--min-accuracy", type=float, help="Exit-Code 1, wenn darunter (für CI)")
    e.set_defaults(func=cmd_eval)

    i = sub.add_parser("init", help="Standard-Regeldatei zum Anpassen anlegen")
    i.add_argument("--path", default="rules.toml")
    i.set_defaults(func=cmd_init)

    lg = sub.add_parser("login", help="Postfach-Zugang im Schlüsselbund des Betriebssystems speichern")
    lg.add_argument("--status", action="store_true", help="nur anzeigen, was gespeichert ist (ohne Werte)")
    lg.add_argument("--no-check", action="store_true", help="ohne Probe-Anmeldung speichern")
    lg.set_defaults(func=cmd_login)

    lo = sub.add_parser("logout", help="Gespeicherte Zugangsdaten aus dem Schlüsselbund löschen")
    lo.set_defaults(func=cmd_logout)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Umlaute auch in der Windows-Konsole
    args = build_parser().parse_args(argv)
    command: Callable[[argparse.Namespace], int] = args.func
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
