"""Bericht mit Freigabe im Browser: Sitzung, HTTP-Schutz und CLI (ADR 0009)."""

import http.client
import threading

import pytest
from fakes import browser_clicking, post_form, request

from paperpilot_ops import cli
from paperpilot_ops.classify import RuleClassifier
from paperpilot_ops.credentials import EnvCredentialStore
from paperpilot_ops.pipeline import run
from paperpilot_ops.store import MemoryStore
from paperpilot_ops.web import ReviewSession, serve
from paperpilot_ops.web.review import CORRECTED, ReviewError
from paperpilot_ops.web.server import SECURITY_HEADERS, make_handler

TOKEN = "geheimes-token"


def _mails(make_mail):
    return [
        make_mail("Ihre Rechnung", "Zahlbar bis 15.12.2026.", sender="<rechnung@stadtwerke.example>"),
        make_mail("Hallo", "Lange nicht gesehen", sender="Sam <sam@example.com>", date="2026-11-21T10:00"),
    ]


def _session(rules, mails, store=None):
    store = store or MemoryStore()
    plan = run(mails, RuleClassifier(rules), rules, store)
    return ReviewSession(mails, plan, rules, store, TOKEN)


def _labels(session):
    return {f"label-{n}": p.classification.label for n, p in enumerate(session.plan.plans)}


# -- ReviewSession (ohne HTTP) ----------------------------------------------------------------------


def test_plan_page_writes_nothing_and_lists_mails(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    page = session.page()
    assert "Lauf freigeben" in page and "Ihre Rechnung" in page and TOKEN in page
    assert "<script" not in page
    assert session.store.files == {} and session.result is None


def test_mail_content_is_escaped(rules, make_mail):
    mails = [make_mail("<script>alert(1)</script>", "x", sender='"><img src=x onerror=alert(1)>')]
    page = _session(rules, mails).page()
    assert "<script>alert" not in page and "<img src=x" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_approve_without_changes_runs_plan(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    result = session.approve({"token": TOKEN, **_labels(session)})
    assert result.applied and session.finished
    assert any("Rechnung" in path for path in session.store.files)
    assert "Erledigt" in session.page() and "ÜBERSICHTEN" in session.page()


def test_correction_wins_and_is_marked(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    unclear = next(n for n, p in enumerate(session.plan.plans) if p.classification.label == "unklar")
    form = {"token": TOKEN, **_labels(session), f"label-{unclear}": "privat/steuern"}
    result = session.approve(form)
    corrected = result.plans[unclear]
    assert corrected.classification.label == "privat/steuern"
    assert corrected.classification.reason == CORRECTED
    assert corrected.action == "file"


def test_missing_label_keeps_plan(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    result = session.approve({"token": TOKEN})
    assert [p.classification.label for p in result.plans] == [p.classification.label for p in session.plan.plans]


@pytest.mark.parametrize(
    "form",
    [{"token": "falsch"}, {}, {"token": TOKEN, "label-0": "erfunden/kategorie"}],
)
def test_invalid_form_writes_nothing(rules, make_mail, form):
    session = _session(rules, _mails(make_mail))
    with pytest.raises(ReviewError):
        session.approve(form)
    assert session.store.files == {} and session.result is None


def test_approve_only_once_and_cancel(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    session.approve({"token": TOKEN})
    with pytest.raises(ReviewError):
        session.approve({"token": TOKEN})
    with pytest.raises(ReviewError):
        session.cancel({"token": TOKEN})

    other = _session(rules, _mails(make_mail))
    other.cancel({"token": TOKEN})
    assert other.cancelled and "Abgebrochen" in other.page() and other.store.files == {}


def test_group_fallback_labels_are_selectable(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    assert "unklar" in session.labels
    assert all(f"{g}/sonstiges" in session.labels for g in rules.groups)


# -- HTTP-Server -------------------------------------------------------------------------------------


@pytest.fixture
def server(rules, make_mail):
    import http.server

    session = _session(rules, _mails(make_mail))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(session))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield session, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_get_needs_token_and_sets_security_headers(server):
    session, port = server
    response, _ = request(port, "GET", "/")
    assert response.status == 404
    response, _ = request(port, "GET", "/?token=falsch")
    assert response.status == 404
    response, body = request(port, "GET", f"/?token={TOKEN}")
    assert response.status == 200 and "Lauf freigeben" in body
    for key, value in SECURITY_HEADERS.items():
        assert response.getheader(key) == value
    assert "script-src" not in SECURITY_HEADERS["Content-Security-Policy"]


def test_foreign_origin_is_rejected(server):
    session, port = server
    response, _ = post_form(port, "/approve", {"token": TOKEN}, origin="http://boese.example")
    assert response.status == 403 and session.result is None and session.store.files == {}


def test_wrong_token_and_unknown_path(server):
    session, port = server
    response, _ = post_form(port, "/approve", {"token": "falsch"})
    assert response.status == 400
    response, _ = post_form(port, "/loeschen", {"token": TOKEN})
    assert response.status == 404
    assert session.result is None


def test_oversized_form_is_rejected(server):
    session, port = server
    headers = {"Content-Length": str(10_000_000), "Origin": f"http://127.0.0.1:{port}"}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/approve")
    for key, value in headers.items():
        conn.putheader(key, value)
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 413 and session.result is None
    conn.close()


def test_approve_redirects_to_result(server):
    session, port = server
    response, _ = post_form(port, "/approve", {"token": TOKEN, **_labels(session)})
    assert response.status == 303
    assert response.getheader("Location") == f"/?token={TOKEN}"
    response, body = request(port, "GET", f"/?token={TOKEN}")
    assert "Erledigt" in body and session.result is not None


def test_cancel_over_http(server):
    session, port = server
    response, _ = post_form(port, "/cancel", {"token": TOKEN}, origin=None)  # ohne Origin (ältere Browser)
    assert response.status == 303 and session.cancelled


# -- serve() und CLI ---------------------------------------------------------------------------------


def test_serve_until_approved(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    serve(session, browser_clicking("approve"), timeout=10, grace=5)
    assert session.result is not None and session.result.applied


def test_serve_times_out_without_writing(rules, make_mail):
    session = _session(rules, _mails(make_mail))
    serve(session, browser_clicking(None), timeout=0.3)
    assert session.result is None and session.store.files == {}


def _run_args(tmp_path):
    return ["run", "--classifier", "rules", "--target", str(tmp_path), "--browser"]


@pytest.fixture
def no_secrets(monkeypatch):
    monkeypatch.setattr(cli, "default_credential_store", lambda: EnvCredentialStore({}))


def test_cli_browser_approval_applies(monkeypatch, capsys, tmp_path, no_secrets):
    monkeypatch.setattr(cli, "_serve_page", lambda s: s.approve({"token": s.token}))
    assert cli.main(_run_args(tmp_path)) == 0
    assert "ÜBERSICHTEN" in capsys.readouterr().out
    assert any(tmp_path.iterdir())


def test_cli_browser_cancel_writes_nothing(monkeypatch, capsys, tmp_path, no_secrets):
    monkeypatch.setattr(cli, "_serve_page", lambda s: s.cancel({"token": s.token}))
    assert cli.main(_run_args(tmp_path)) == 1
    assert "nichts wurde geschrieben" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())


def test_cli_browser_ctrl_c_writes_nothing(monkeypatch, tmp_path, no_secrets):
    def interrupt(session):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_serve_page", interrupt)
    assert cli.main(_run_args(tmp_path)) == 1
    assert not any(tmp_path.iterdir())


def test_cli_browser_and_apply_exclude_each_other(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([*_run_args(tmp_path), "--apply"])


def test_cli_browser_without_new_mails_skips_page(monkeypatch, capsys, tmp_path, no_secrets):
    empty = tmp_path / "leer.json"
    empty.write_text("[]", "utf-8")
    monkeypatch.setattr(cli, "_serve_page", lambda s: pytest.fail("ohne Mails keine Seite"))
    assert cli.main([*_run_args(tmp_path / "ablage"), "--input", str(empty)]) == 0
