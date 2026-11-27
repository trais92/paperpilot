"""Einrichtungsassistent im Browser (Roadmap 8, ADR 0010)."""

import urllib.parse

import pytest
from fakes import BrokenKeyring, FakeKeyring, browser_clicking, post_form, request

from paperpilot_ops import cli
from paperpilot_ops.credentials import CredentialStoreError, KeyringCredentialStore
from paperpilot_ops.settings import UserSettings, load_settings
from paperpilot_ops.web import SetupSession, serve
from paperpilot_ops.web.page import FormError, UnknownAction

TOKEN = "einrichtungs-token"
PASSWORD = "app-passwort-geheim"
GROQ_KEY = "gsk_geheimer_schluessel"


class Calls:
    def __init__(self, imap_error=None, google_error=None):
        self.imap = []
        self.google = []
        self.imap_error = imap_error
        self.google_error = google_error

    def check_imap(self, host, user, password):
        self.imap.append((host, user))
        if self.imap_error:
            raise self.imap_error

    def google_login(self, client_id, client_secret):
        self.google.append(client_id)
        if self.google_error:
            raise self.google_error
        return "refresh-token-geheim"


@pytest.fixture
def keyring():
    return FakeKeyring()


def _session(rules, tmp_path, keyring=None, calls=None, vault_error=""):
    calls = calls or Calls()
    vault = KeyringCredentialStore(keyring) if keyring is not None else None
    return SetupSession(
        rules=rules,
        settings=UserSettings(),
        settings_file=tmp_path / "settings.toml",
        vault=vault,
        token=TOKEN,
        check_imap=calls.check_imap,
        google_login=calls.google_login,
        vault_error=vault_error,
    )


def _secret_values(keyring):
    return [v for (_, _), v in keyring.entries.items()]


# -- Postfach und Schlüssel ------------------------------------------------------------------------


def test_mail_is_checked_then_stored_and_never_shown(rules, tmp_path, keyring):
    calls = Calls()
    session = _session(rules, tmp_path, keyring, calls)
    session.submit("mail", {"token": TOKEN, "host": "", "user": "ich@firma.example", "password": PASSWORD})
    assert calls.imap == [("imap.gmail.com", "ich@firma.example")]
    vault = session.vault
    assert vault.get("imap_password") == PASSWORD and vault.get("imap_host") == "imap.gmail.com"
    page = session.page()
    assert PASSWORD not in page and "Postfach geprüft und gespeichert" in page
    assert "ich@firma.example" in page  # Benutzername wird vorausgefüllt


def test_failed_imap_check_stores_nothing_and_hides_server_text(rules, tmp_path, keyring):
    calls = Calls(imap_error=RuntimeError(f"LOGIN failed for {PASSWORD}"))
    session = _session(rules, tmp_path, keyring, calls)
    session.submit("mail", {"token": TOKEN, "user": "ich@firma.example", "password": PASSWORD})
    assert keyring.entries == {}
    page = session.page()
    assert "fehlgeschlagen (RuntimeError)" in page and PASSWORD not in page


def test_mail_requires_user_and_password(rules, tmp_path, keyring):
    calls = Calls()
    session = _session(rules, tmp_path, keyring, calls)
    session.submit("mail", {"token": TOKEN, "user": "ich@firma.example"})
    assert calls.imap == [] and keyring.entries == {} and "Pflicht" in session.page()


def test_ai_key_is_stored_and_never_shown(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    session.submit("ai", {"token": TOKEN, "groq_key": f"  {GROQ_KEY} "})
    assert session.vault.get("groq_api_key") == GROQ_KEY
    assert GROQ_KEY not in session.page()
    session.submit("ai", {"token": TOKEN, "groq_key": ""})
    assert "Kein Schlüssel" in session.page()


def test_claude_is_shown_as_paid_and_not_preset(rules, tmp_path, keyring):
    page = _session(rules, tmp_path, keyring).page()
    assert "<strong>kostenpflichtig</strong>" in page and 'name="claude' not in page


def test_without_keyring_nothing_is_stored_and_reason_is_shown(rules, tmp_path):
    session = _session(rules, tmp_path, vault_error="Kein Schlüsselbund auf diesem System gefunden.")
    session.submit("ai", {"token": TOKEN, "groq_key": GROQ_KEY})
    page = session.page()
    assert "Kein Schlüsselbund verfügbar" in page and GROQ_KEY not in page


def test_broken_keyring_message_has_no_value(rules, tmp_path):
    session = _session(rules, tmp_path, BrokenKeyring())
    session.submit("ai", {"token": TOKEN, "groq_key": GROQ_KEY})
    page = session.page()
    assert "nicht beschreibbar" in page and GROQ_KEY not in page


def test_google_connect_stores_tokens(rules, tmp_path, keyring):
    calls = Calls()
    session = _session(rules, tmp_path, keyring, calls)
    session.submit("google", {"token": TOKEN, "client_id": "id.apps.example", "client_secret": "s"})
    assert calls.google == ["id.apps.example"]
    assert session.vault.get("google_refresh_token") == "refresh-token-geheim"
    assert "refresh-token-geheim" not in session.page() and "Google Drive verbunden" in session.page()
    # Zweites Mal ohne Eingabe: gespeicherte Werte werden genutzt
    session.submit("google", {"token": TOKEN})
    assert calls.google == ["id.apps.example", "id.apps.example"]


def test_google_errors(rules, tmp_path, keyring):
    class OAuthError(Exception):
        pass

    session = _session(rules, tmp_path, keyring, Calls(google_error=OAuthError("Zugriff verweigert.")))
    session.submit("google", {"token": TOKEN})
    assert "Pflicht" in session.page()
    session.submit("google", {"token": TOKEN, "client_id": "id", "client_secret": "s"})
    assert "Zugriff verweigert." in session.page() and keyring.entries == {}

    other = _session(rules, tmp_path, keyring, Calls(google_error=RuntimeError("token=geheim")))
    other.submit("google", {"token": TOKEN, "client_id": "id", "client_secret": "s"})
    assert "RuntimeError" in other.page() and "geheim" not in other.page()


# -- Kategorien und Ablageziel ---------------------------------------------------------------------


def test_categories_are_saved_to_settings(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    form = {"token": TOKEN, "cat-privat/rechnungen": "on", "cat-bewerbung/einladung": "on"}
    session.submit("categories", form)
    saved = load_settings(tmp_path / "settings.toml")
    assert saved.categories["privat/rechnungen"] is True
    assert saved.categories["bewerbung/absage"] is False
    assert "werbung" not in saved.categories  # nie ablegbar, steht nicht zur Wahl
    assert "2 von" in session.page()
    assert 'name="cat-privat/rechnungen" checked' in session.page()


def test_storage_local_and_drive(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    session.submit("storage", {"token": TOKEN, "target": "local", "target_dir": "D:/Ablage"})
    assert load_settings(tmp_path / "settings.toml").target_dir == "D:/Ablage"
    session.submit("storage", {"token": TOKEN, "target": "drive", "drive_folder": "Belege"})
    saved = load_settings(tmp_path / "settings.toml")
    assert saved.storage_target == "drive" and saved.drive_folder == "Belege"
    assert session.effective_rules.storage.target == "drive"


def test_invalid_storage_saves_nothing(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    session.submit("storage", {"token": TOKEN, "target": "ftp"})
    session.submit("storage", {"token": TOKEN, "target": "drive", "drive_folder": "a/b"})
    assert not (tmp_path / "settings.toml").exists()
    assert "Nichts gespeichert" in session.page()


# -- Ablauf und Schutz -----------------------------------------------------------------------------


def test_token_and_unknown_action(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    with pytest.raises(FormError):
        session.submit("ai", {"token": "falsch", "groq_key": GROQ_KEY})
    with pytest.raises(UnknownAction):
        session.submit("loeschen", {"token": TOKEN})
    assert keyring.entries == {}


def test_finish_variants(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)
    session.submit("finish", {"token": TOKEN, "next": "review"})
    assert session.finished and session.review_requested
    assert "erste Lauf" in session.page()
    with pytest.raises(FormError):
        session.submit("ai", {"token": TOKEN, "groq_key": GROQ_KEY})

    other = _session(rules, tmp_path, keyring)
    other.submit("finish", {"token": TOKEN, "next": "close"})
    assert other.finished and not other.review_requested


def test_page_has_no_script_and_escapes_values(rules, tmp_path, keyring):
    keyring.set_password("paperpilot", "imap_user", '"><script>alert(1)</script>')
    keyring.set_password("paperpilot", "imap_password", "x")
    page = _session(rules, tmp_path, keyring).page()
    assert "<script" not in page and "&lt;script&gt;" in page
    assert 'type="password" name="password">' in page  # Passwortfeld immer leer


def test_serve_setup_over_http(rules, tmp_path, keyring):
    session = _session(rules, tmp_path, keyring)

    def browser(url):
        parts = urllib.parse.urlsplit(url)
        request(parts.port, "GET", f"/?{parts.query}")
        response, _ = post_form(parts.port, "/ai", {"token": TOKEN, "groq_key": GROQ_KEY})
        assert response.status == 303
        response, _ = post_form(parts.port, "/ai", {"token": TOKEN}, origin="http://boese.example")
        assert response.status == 403
        browser_clicking("finish")(url)

    serve(session, browser, timeout=10, grace=5)
    assert session.finished and session.vault.get("groq_api_key") == GROQ_KEY


# -- CLI -------------------------------------------------------------------------------------------


def test_cli_setup_close(monkeypatch, capsys, keyring):
    monkeypatch.setattr(cli, "_open_vault", lambda: KeyringCredentialStore(keyring))
    monkeypatch.setattr(cli, "_serve_page", lambda s: s.submit("finish", {"token": s.token, "next": "close"}))
    assert cli.main(["setup"]) == 0
    assert "paperpilot run --source imap --browser" in capsys.readouterr().out


def test_cli_setup_not_finished(monkeypatch, capsys):
    def no_keyring():
        raise CredentialStoreError("Kein Schlüsselbund.")

    def interrupt(session):
        assert session.vault is None and "Kein Schlüsselbund" in session.page()
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_open_vault", no_keyring)
    monkeypatch.setattr(cli, "_serve_page", interrupt)
    assert cli.main(["setup"]) == 1
    assert "nicht abgeschlossen" in capsys.readouterr().out


def test_cli_setup_then_first_run(monkeypatch, keyring):
    seen = []

    def serve_page(page):
        seen.append(type(page).__name__)
        if isinstance(page, SetupSession):
            page.submit("finish", {"token": page.token, "next": "review"})
        else:
            page.cancel({"token": page.token})

    monkeypatch.setattr(cli, "_open_vault", lambda: KeyringCredentialStore(keyring))
    monkeypatch.setattr(cli, "_serve_page", serve_page)
    monkeypatch.setattr(cli, "_classifier_or_exit", lambda name, rules, creds: cli.make_classifier("rules", rules))
    monkeypatch.setattr(cli, "_imap_source", lambda creds: cli.JsonSource(cli._data("demo_inbox.json")))
    assert cli.main(["setup"]) == 1  # erster Lauf abgebrochen: nichts geschrieben
    assert seen == ["SetupSession", "ReviewSession"]
