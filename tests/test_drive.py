"""Google Drive: Anmeldung (OAuth mit PKCE), REST-Hülle, Ablageziel und Verdrahtung. Kein Netz.

Der allgemeine Vertrag des Ablageziels wird in tests/test_storage_contract.py geprüft.
"""

import base64
import hashlib
import json
import threading
import urllib.parse
import urllib.request

import pytest
from fake_drive import SHEET, FakeDrive, FakeTokens
from fakes import FakeTransport

from paperpilot_ops import cli
from paperpilot_ops.ai.http import HttpResponse
from paperpilot_ops.classify import RuleClassifier
from paperpilot_ops.composition import MissingGoogleLoginError, make_store
from paperpilot_ops.credentials import EnvCredentialStore, KeyringCredentialStore
from paperpilot_ops.drive import DRIVE_SCOPE, DriveApi, DriveError, DriveStore, GoogleSession
from paperpilot_ops.drive.api import quote_query
from paperpilot_ops.drive.oauth import (
    OAuthError,
    authorization_url,
    exchange_code,
    login,
    pkce_pair,
    receive_code,
)
from paperpilot_ops.pipeline import run
from paperpilot_ops.store import LocalStore

REFRESH = "1//refresh-geheim"


def token_response(**data):
    return HttpResponse(200, json.dumps(data).encode())


# -- OAuth ----------------------------------------------------------------------------------


def test_pkce_challenge_is_s256_of_verifier():
    pair = pkce_pair()
    digest = base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode()).digest()).rstrip(b"=").decode()
    assert pair.challenge == digest and 43 <= len(pair.verifier) <= 128
    assert pkce_pair().verifier != pair.verifier


def test_authorization_url_requests_only_drive_file():
    url = authorization_url("client.apps.example", "http://127.0.0.1:5000/", "challenge", "state-1")
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith("https://accounts.google.com/")
    assert query["scope"] == DRIVE_SCOPE == "https://www.googleapis.com/auth/drive.file"
    assert query["code_challenge_method"] == "S256" and query["state"] == "state-1"
    assert query["access_type"] == "offline" and query["redirect_uri"] == "http://127.0.0.1:5000/"


def test_exchange_code_sends_verifier_and_returns_refresh_token():
    transport = FakeTransport(token_response(access_token="a", refresh_token=REFRESH, expires_in=3599))
    token = exchange_code("cid", "secret", "code-1", "verifier-1", "http://127.0.0.1:1/", transport)
    form = dict(urllib.parse.parse_qsl(transport.requests[0].body.decode()))
    assert token == REFRESH
    assert form["grant_type"] == "authorization_code" and form["code_verifier"] == "verifier-1"


@pytest.mark.parametrize(
    "response",
    [HttpResponse(400, b'{"error": "invalid_grant"}'), HttpResponse(500, b"kaputt"), token_response(access_token="a")],
)
def test_exchange_code_failures(response):
    with pytest.raises(OAuthError) as err:
        exchange_code("cid", "secret", "code", "v", "http://127.0.0.1:1/", FakeTransport(response))
    assert "secret" not in str(err.value)


def test_session_caches_and_refreshes_after_expiry():
    now = [1000.0]
    transport = FakeTransport(token_response(access_token="t1", expires_in=3600), token_response(access_token="t2"))
    session = GoogleSession("cid", "secret", REFRESH, transport, clock=lambda: now[0])
    assert session.access_token() == "t1" and session.access_token() == "t1"
    now[0] += 3600
    assert session.access_token() == "t2"
    assert len(transport.requests) == 2 and REFRESH not in repr(session)


def test_session_invalidate_forces_new_token():
    transport = FakeTransport(token_response(access_token="t1"), token_response(access_token="t2"))
    session = GoogleSession("cid", "secret", REFRESH, transport)
    session.access_token()
    session.invalidate()
    assert session.access_token() == "t2"


def test_session_without_access_token_is_error():
    with pytest.raises(OAuthError):
        GoogleSession("cid", "s", REFRESH, FakeTransport(token_response(token_type="Bearer"))).access_token()


def test_receive_code_runs_local_callback_server():
    def browser(url):
        redirect = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["redirect_uri"]
        assert redirect.startswith("http://127.0.0.1:")
        threading.Thread(
            target=lambda: urllib.request.urlopen(f"{redirect}?code=abc&state=s1", timeout=5).read()
        ).start()

    code, redirect = receive_code("s1", browser, lambda uri: authorization_url("cid", uri, "ch", "s1"))
    assert code == "abc" and redirect.startswith("http://127.0.0.1:")


@pytest.mark.parametrize(
    ("query", "message"), [("code=abc&state=fremd", "state"), ("error=access_denied&state=s1", "abgebrochen")]
)
def test_receive_code_rejects_wrong_state_and_denial(query, message):
    def browser(url):
        redirect = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["redirect_uri"]
        threading.Thread(target=lambda: urllib.request.urlopen(f"{redirect}?{query}", timeout=5).read()).start()

    with pytest.raises(OAuthError, match=message):
        receive_code("s1", browser, lambda uri: authorization_url("cid", uri, "ch", "s1"))


def test_login_flow_combines_callback_and_exchange():
    seen = {}

    def fake_receive(state, open_browser, build_url):
        seen["url"] = build_url("http://127.0.0.1:9999/")
        return "code-9", "http://127.0.0.1:9999/"

    transport = FakeTransport(token_response(refresh_token=REFRESH))
    assert login("cid", "secret", print, transport, receive=fake_receive) == REFRESH
    assert "drive.file" in urllib.parse.unquote(seen["url"])


# -- REST-Hülle -----------------------------------------------------------------------------


def test_quote_query_escapes_quotes_and_backslashes():
    assert quote_query("O'Brien\\Akte") == "'O\\'Brien\\\\Akte'"


def test_api_retries_once_after_401_with_fresh_token():
    drive, tokens = FakeDrive(token="neu"), FakeTokens("alt")

    def invalidate():
        tokens.invalidated += 1
        tokens.token = "neu"

    tokens.invalidate = invalidate
    assert DriveApi(tokens, drive).find("root", "PaperPilot") is None
    assert tokens.invalidated == 1


def test_api_gives_up_after_second_401():
    with pytest.raises(DriveError, match="login --google"):
        DriveApi(FakeTokens("falsch"), FakeDrive(token="richtig")).find("root", "x")


def test_api_errors_contain_no_token():
    drive = FakeDrive()
    drive.fail_next = [500]
    with pytest.raises(DriveError) as err:
        DriveApi(FakeTokens(), drive).create_folder("root", "x")
    assert "tok-1" not in str(err.value) and "500" in str(err.value)


def test_api_has_no_delete_or_trash():
    assert not [name for name in dir(DriveApi) if "delete" in name or "trash" in name]


# -- Ablageziel -----------------------------------------------------------------------------


def _store(drive=None, root="PaperPilot"):
    drive = drive or FakeDrive()
    return drive, DriveStore(DriveApi(FakeTokens(), drive), root)


def test_documents_land_in_same_structure_as_local(tmp_path, rules, make_mail):
    mails = [
        make_mail("Ihre Rechnung", "Rechnungsbetrag 10 EUR, zahlbar bis 15.12.2026.", sender="<r@stadtwerke.example>",
                  attachments=[("Rechnung.pdf", b"%PDF demo")]),
    ]  # fmt: skip
    drive, store = _store()
    run(mails, RuleClassifier(rules), rules, store, apply=True)
    run(mails, RuleClassifier(rules), rules, LocalStore(tmp_path), apply=True)
    local = {str(p.relative_to(tmp_path)).replace("\\", "/") for p in tmp_path.rglob("*") if p.is_file()}
    remote = {
        path.removeprefix("PaperPilot/")
        for path, f in drive.by_path().items()
        if f["mimeType"] != "application/vnd.google-apps.folder"
    }
    local_docs = {p for p in local if not p.endswith("Übersicht.csv")}
    remote_docs = {p for p in remote if not p.endswith("Übersicht")}
    assert local_docs == remote_docs


def test_overview_is_a_google_sheet(rules, make_mail):
    drive, store = _store()
    store.append_rows(
        "06 Rechnungen & Belege/Übersicht", ["Datum", "Betreff"], [{"Datum": "2026-11-21", "Betreff": "Ä"}]
    )
    sheet = drive.by_path()["PaperPilot/06 Rechnungen & Belege/Übersicht"]
    assert sheet["mimeType"] == SHEET
    assert sheet["content"].decode() == "Datum,Betreff\r\n2026-11-21,Ä\r\n"


def test_root_folder_is_created_once_and_reused():
    drive, store = _store(root="Meine Belege")
    store.write_file("a/b.txt", b"1")
    store.write_file("a/c.txt", b"2")
    _, again = _store(drive, root="Meine Belege")
    again.write_file("a/d.txt", b"3")
    folders = [f for f in drive.files.values() if f["mimeType"] == "application/vnd.google-apps.folder"]
    assert sorted(f["name"] for f in folders) == ["Meine Belege", "a"]
    assert store.location == "Google Drive: Meine Ablage/Meine Belege"


def test_reading_missing_paths_creates_nothing():
    drive, store = _store()
    assert store.read_text("x/y.txt") is None and store.read_rows("x/Übersicht") == [] and store.last_run() is None
    assert drive.files == {}


# -- Verdrahtung ----------------------------------------------------------------------------


def test_make_store_local_and_drive(rules, tmp_path):
    assert isinstance(make_store(rules, EnvCredentialStore({}), local_dir=str(tmp_path)), LocalStore)
    creds = EnvCredentialStore(
        {
            "PAPERPILOT_GOOGLE_CLIENT_ID": "c",
            "PAPERPILOT_GOOGLE_CLIENT_SECRET": "s",
            "PAPERPILOT_GOOGLE_REFRESH_TOKEN": "r",
        }
    )
    store = make_store(rules, creds, target="drive")
    assert isinstance(store, DriveStore) and store.location.endswith("/PaperPilot")
    with pytest.raises(MissingGoogleLoginError, match="login --google"):
        make_store(rules, EnvCredentialStore({}), target="drive")
    with pytest.raises(ValueError):
        make_store(rules, creds, target="ftp")


def test_storage_section_is_validated(tmp_path):
    from paperpilot_ops.config import load_rules

    path = tmp_path / "r.toml"
    path.write_text('[storage]\ntarget = "drive"\ndrive_folder = "Belege"\n', "utf-8")
    assert load_rules(path).storage.target == "drive" and load_rules(path).storage.drive_folder == "Belege"
    for bad in ('[storage]\ntarget = "ftp"\n', '[storage]\ndrive_folder = "a/b"\n'):
        path.write_text(bad, "utf-8")
        with pytest.raises(ValueError):
            load_rules(path)


def test_run_with_drive_but_without_login_stops(monkeypatch, capsys):
    monkeypatch.setattr(cli, "default_credential_store", lambda: EnvCredentialStore({}))
    assert cli.main(["run", "--classifier", "rules", "--storage", "drive"]) == 2
    assert "login --google" in capsys.readouterr().err


class _Keyring:
    def __init__(self):
        self.entries = {}

    def get_password(self, s, u):
        return self.entries.get((s, u))

    def set_password(self, s, u, p):
        self.entries[(s, u)] = p

    def delete_password(self, s, u):
        del self.entries[(s, u)]


@pytest.fixture
def vault(monkeypatch, tmp_path):
    store = KeyringCredentialStore(_Keyring())
    monkeypatch.setattr(cli, "_open_vault", lambda: store)
    monkeypatch.chdir(tmp_path)
    return store


def test_login_google_stores_token_in_keyring(vault, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("builtins.input", lambda *_: "client.apps.example")
    monkeypatch.setattr("getpass.getpass", lambda *_: "client-secret")
    monkeypatch.setattr(cli, "_google_login_flow", lambda cid, secret: REFRESH)
    assert cli.main(["login", "--google"]) == 0
    assert vault.get("google_refresh_token") == REFRESH and vault.get("google_client_id") == "client.apps.example"
    out = capsys.readouterr().out
    assert REFRESH not in out and "client-secret" not in out and list(tmp_path.iterdir()) == []


def test_login_google_failure_stores_nothing(vault, monkeypatch):
    def fail(cid, secret):
        raise OAuthError("Anmeldung abgebrochen (access_denied).")

    monkeypatch.setattr("builtins.input", lambda *_: "cid")
    monkeypatch.setattr("getpass.getpass", lambda *_: "secret")
    monkeypatch.setattr(cli, "_google_login_flow", fail)
    assert cli.main(["login", "--google"]) == 1
    assert vault.get("google_client_id") is None


def test_login_google_requires_client(vault, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr("getpass.getpass", lambda *_: "")
    assert cli.main(["login", "--google"]) == 1
