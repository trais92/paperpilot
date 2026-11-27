"""Kommandozeile: paperpilot setup | demo | run | eval | init | login | logout"""

from __future__ import annotations

import argparse
import getpass
import secrets
import shutil
import sys
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path

from . import __version__
from .ai import MissingAIKeyError
from .ai.providers import credential_key
from .composition import CLASSIFIERS, MissingGoogleLoginError, describe_classifier, make_classifier, make_store
from .config import AI_PROVIDERS, STORAGE_TARGETS, Rules, default_rules_text, load_rules
from .credentials import KEYS, CredentialStoreError, KeyringCredentialStore, default_credential_store
from .evaluate import evaluate, render_eval
from .models import Mail
from .pipeline import RunResult, render_report, run
from .ports import Classifier, CredentialStore, MailSource, MutableCredentialStore, StorageTarget
from .settings import apply_settings, load_settings, settings_path
from .sources import ImapSource, JsonSource
from .store import LocalStore
from .web import ReviewSession, SetupSession, serve
from .web.page import LocalPage


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
    print("\nDie Demo sortiert offline mit Stichwörtern. Echte Läufe nutzen die KI (siehe README).")
    print("Tipp: 'paperpilot demo' nochmal ausführen zeigt die Idempotenz (0 neue Mails).")
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
        if args.ai:
            return _login_ai(vault, args.ai)
        if args.google:
            return _login_google(vault)
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


def _login_ai(vault: MutableCredentialStore, provider: str) -> int:
    """API-Schlüssel eines KI-Anbieters im Schlüsselbund speichern."""
    api_key = getpass.getpass(f"API-Schlüssel für {provider}: ").strip()
    if not api_key:
        print("Kein Schlüssel eingegeben. Nichts gespeichert.", file=sys.stderr)
        return 1
    vault.set(credential_key(provider), api_key)
    print(f"Schlüssel für {provider} im Schlüsselbund gespeichert. Löschen mit 'paperpilot logout'.")
    return 0


def _google_login_flow(client_id: str, client_secret: str) -> str:
    """Anmeldung im Browser; eigene Funktion, damit Tests ohne Browser und Netz auskommen."""
    import webbrowser

    from .drive.oauth import login

    print("Der Browser öffnet sich für die Anmeldung bei Google (nur Zugriff auf von PaperPilot angelegte Dateien).")
    return login(client_id, client_secret, webbrowser.open)


def _login_google(vault: MutableCredentialStore) -> int:
    """Google Drive verbinden: OAuth-Client einmal hinterlegen, im Browser zustimmen, Token speichern."""
    from .drive.oauth import OAuthError

    stored_id = vault.get("google_client_id")
    client_id = input(f"OAuth-Client-ID [{'gespeichert' if stored_id else 'fehlt'}]: ").strip() or stored_id
    client_secret = getpass.getpass("OAuth-Client-Secret (leer lassen = gespeicherten nutzen): ").strip()
    client_secret = client_secret or vault.get("google_client_secret") or ""
    if not client_id or not client_secret:
        print(
            "Client-ID und Client-Secret sind Pflicht (siehe docs/google-drive.md). Nichts gespeichert.",
            file=sys.stderr,
        )
        return 1
    try:
        refresh_token = _google_login_flow(client_id, client_secret)
    except OAuthError as exc:
        print(f"{exc} Nichts gespeichert.", file=sys.stderr)
        return 1
    vault.set("google_client_id", client_id)
    vault.set("google_client_secret", client_secret)
    vault.set("google_refresh_token", refresh_token)
    print('Google Drive verbunden. In der Konfiguration [storage] target = "drive" setzen oder --storage drive nutzen.')
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


def _classifier_or_exit(name: str, rules: Rules, creds: CredentialStore) -> Classifier | None:
    """Baut den Klassifizierer vor dem Abruf, damit ein fehlender Schlüssel sofort auffällt."""
    try:
        classifier = make_classifier(name, rules, creds)
    except MissingAIKeyError as exc:
        print(f"{exc}\nOhne KI (nur Stichwörter): --classifier rules", file=sys.stderr)
        return None
    print(f"Sortiert mit: {describe_classifier(classifier)}")
    return classifier


def _load_rules(path: str | None) -> Rules:
    """Regeldatei plus persönliche Einstellungen aus dem Assistenten (settings.toml, ADR 0010)."""
    return apply_settings(load_rules(path), load_settings(settings_path()))


def cmd_run(args: argparse.Namespace) -> int:
    rules = _load_rules(args.rules)
    creds = default_credential_store()
    classifier = _classifier_or_exit(args.classifier, rules, creds)
    if classifier is None:
        return 2
    try:
        store = make_store(rules, creds, args.storage, args.target)
    except MissingGoogleLoginError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    since = datetime.fromisoformat(args.since) if args.since else store.last_run()
    source: MailSource
    if args.source == "imap":
        source = _imap_source(creds)
    else:
        source = JsonSource(args.input or _data("demo_inbox.json"))
    mails = list(source.fetch(since))
    result = run(mails, classifier, rules, store, apply=args.apply)
    if args.browser:
        return _review_in_browser(mails, result, rules, store)
    print(render_report(result, store.location))
    return 0


def _review_in_browser(mails: list[Mail], plan: RunResult, rules: Rules, store: StorageTarget) -> int:
    """Zeigt den Plan als lokale Seite und führt erst nach „Freigeben“ aus (ADR 0009)."""
    if not plan.plans:
        print(render_report(plan, store.location))
        return 0
    session = ReviewSession(mails, plan, rules, store, secrets.token_urlsafe(32))
    print("Bericht im Browser geöffnet. Dort prüfen, korrigieren und freigeben (Abbrechen mit Strg+C).")
    try:
        _serve_page(session)
    except KeyboardInterrupt:
        pass  # Abbruch im Terminal: nichts geschrieben, wie „Abbrechen“ auf der Seite
    if session.result is not None:
        print(render_report(session.result, store.location))
        return 0
    print("Nicht freigegeben, nichts wurde geschrieben.")
    return 1


def _serve_page(page: LocalPage) -> None:
    """Naht für Tests: startet den lokalen Server und öffnet den Standardbrowser."""
    import webbrowser

    serve(page, webbrowser.open)


def cmd_setup(args: argparse.Namespace) -> int:
    """Einrichtungsassistent im Browser (Roadmap 8). Danach auf Wunsch gleich der erste Lauf zur Freigabe."""
    path = settings_path()
    vault: MutableCredentialStore | None = None
    vault_error = ""
    try:
        vault = _open_vault()
    except CredentialStoreError as exc:
        vault_error = str(exc)
    session = SetupSession(
        rules=load_rules(args.rules),
        settings=load_settings(path),
        settings_file=path,
        vault=vault,
        token=secrets.token_urlsafe(32),
        check_imap=lambda host, user, password: _verify_imap(ImapSource(host, user, password)),
        google_login=_google_login_flow,
        vault_error=vault_error,
    )
    print("Einrichtung im Browser geöffnet (Abbrechen mit Strg+C). Einstellungen: " + str(path))
    try:
        _serve_page(session)
    except KeyboardInterrupt:
        pass
    if not session.done:
        print("Einrichtung nicht abgeschlossen. Was schon gespeichert wurde, bleibt erhalten.")
        return 1
    if not session.review_requested:
        print("Einrichtung abgeschlossen. Erster Lauf: paperpilot run --source imap --browser")
        return 0
    run_args = build_parser().parse_args(["run", "--source", "imap", "--browser"])
    run_args.rules = args.rules
    return int(cmd_run(run_args))


def cmd_eval(args: argparse.Namespace) -> int:
    rules = _load_rules(args.rules)
    classifier = _classifier_or_exit(args.classifier, rules, default_credential_store())
    if classifier is None:
        return 2
    samples = JsonSource(args.testset or _data("eval_set.jsonl")).load()
    report = evaluate(classifier, samples)
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
    p = argparse.ArgumentParser(prog="paperpilot", description="PaperPilot: Mails mit KI einsortieren und ablegen.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("setup", help="Einrichtung im Browser: Postfach, KI, Kategorien, Ablageziel")
    st.add_argument("--rules")
    st.set_defaults(func=cmd_setup)

    d = sub.add_parser("demo", help="Komplettlauf auf anonymen Beispielmails")
    d.add_argument("--out", default="demo-ablage")
    d.add_argument("--reset", action="store_true", help="Demo-Ordner vorher leeren")
    d.add_argument("--rules")
    d.set_defaults(func=cmd_demo)

    r = sub.add_parser("run", help="Postfach einsortieren (Standard: Trockenlauf)")
    r.add_argument("--source", choices=["json", "imap"], default="json")
    r.add_argument("--input", help="JSON/JSONL-Datei bei --source json")
    r.add_argument("--rules")
    r.add_argument("--storage", choices=STORAGE_TARGETS, help="Ablageziel (überschreibt [storage] target)")
    r.add_argument("--target", help="lokaler Ablage-Ordner (überschreibt target_dir)")
    r.add_argument("--classifier", choices=CLASSIFIERS, default="ai", help="ai (Standard) oder rules (ohne KI)")
    r.add_argument("--since", help="ISO-Datum, sonst seit letztem Lauf")
    mode = r.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Plan wirklich ausführen")
    mode.add_argument("--browser", action="store_true", help="Plan im Browser prüfen, korrigieren und freigeben")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("eval", help="Trefferquote auf gelabeltem Testset messen")
    e.add_argument("--testset")
    e.add_argument("--rules")
    e.add_argument(
        "--classifier", choices=CLASSIFIERS, default="rules", help="rules (Standard, Vergleichswert) oder ai"
    )
    e.add_argument("--min-accuracy", type=float, help="Exit-Code 1, wenn darunter (für CI)")
    e.set_defaults(func=cmd_eval)

    i = sub.add_parser("init", help="Standard-Regeldatei zum Anpassen anlegen")
    i.add_argument("--path", default="rules.toml")
    i.set_defaults(func=cmd_init)

    lg = sub.add_parser("login", help="Postfach-Zugang oder KI-Schlüssel im Schlüsselbund speichern")
    lg.add_argument("--status", action="store_true", help="nur anzeigen, was gespeichert ist (ohne Werte)")
    lg.add_argument("--no-check", action="store_true", help="ohne Probe-Anmeldung speichern")
    lg.add_argument("--ai", choices=AI_PROVIDERS, help="statt des Postfachs den API-Schlüssel dieses KI-Anbieters")
    lg.add_argument("--google", action="store_true", help="statt des Postfachs Google Drive verbinden")
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
