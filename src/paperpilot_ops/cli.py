"""Kommandozeile: paperpilot demo | run | eval | init"""

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
from .credentials import EnvCredentialStore
from .evaluate import evaluate, render_eval
from .pipeline import render_report, run
from .ports import CredentialStore, MailSource
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


def _imap_source(creds: CredentialStore) -> ImapSource:
    """IMAP-Quelle aus gespeicherten Zugangsdaten, fehlende werden abgefragt (und nicht gespeichert)."""
    host = creds.get("imap_host") or "imap.gmail.com"
    user = creds.get("imap_user") or input("IMAP-Benutzer: ")
    password = creds.get("imap_password") or getpass.getpass("App-Passwort (wird nicht gespeichert): ")
    return ImapSource(host, user, password)


def cmd_run(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    store = LocalStore(args.target or rules.target_dir)
    since = datetime.fromisoformat(args.since) if args.since else store.last_run()
    source: MailSource
    if args.source == "imap":
        source = _imap_source(EnvCredentialStore())
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
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Umlaute auch in der Windows-Konsole
    args = build_parser().parse_args(argv)
    command: Callable[[argparse.Namespace], int] = args.func
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
