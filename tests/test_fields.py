"""Angaben aus Mail und PDF (Roadmap 4): Prüfung, KI-Antwort, PDF-Text, Korrektur im Browser."""

import json
from dataclasses import replace

import pytest
from fakes import ScriptedModel

from paperpilot_ops.ai import AIClassifier
from paperpilot_ops.ai.classifier import FIELDS_SCHEMA
from paperpilot_ops.classify import UNCLEAR, FixedClassifier
from paperpilot_ops.composition import make_classifier
from paperpilot_ops.config import load_rules
from paperpilot_ops.credentials import EnvCredentialStore
from paperpilot_ops.fields import (
    FieldError,
    check_amount,
    check_date,
    check_reference,
    parse_fields,
    parse_form_fields,
)
from paperpilot_ops.models import Attachment, Classification, Fields
from paperpilot_ops.pdftext import attachment_text
from paperpilot_ops.pipeline import run
from paperpilot_ops.store import MemoryStore
from paperpilot_ops.web import ReviewSession
from paperpilot_ops.web.review import CORRECTED, ReviewError

# -- Prüfungen -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "currency", "expected"),
    [
        (49.9, "EUR", "49.90 EUR"),
        (1200, "CHF", "1200.00 CHF"),
        ("49,90 EUR", "EUR", "49.90 EUR"),
        ("-12.5 EUR", "EUR", "-12.50 EUR"),
    ],
)
def test_amount_is_normalised(value, currency, expected):
    assert check_amount(value, currency) == expected


@pytest.mark.parametrize("value", [True, "viel", "49,90", "1.234,56 EUR", 1e12, None, "49.90 eur"])
def test_bad_amounts_are_rejected(value):
    with pytest.raises(FieldError):
        check_amount(value)


def test_dates_and_references():
    assert check_date(" 2026-12-15 ") == "2026-12-15"
    for bad in ("15.12.2026", "2026-02-30", "1999-12-31", 20261215):
        with pytest.raises(FieldError):
            check_date(bad)
    assert check_reference("RE-2026/0017") == "RE-2026/0017"
    for bad in ("zwei Wörter", "x" * 41, "-beginnt-mit-strich", "<script>", 17):
        with pytest.raises(FieldError):
            check_reference(bad)


def test_error_messages_never_contain_the_value():
    with pytest.raises(FieldError) as info:
        check_reference("GEHEIM 123")
    assert "GEHEIM" not in str(info.value)


def test_parse_fields_keeps_valid_and_names_rejected():
    raw = {"amount": 49.9, "currency": "EUR", "document_date": "gestern", "reference": "R-1", "due_date": None}
    fields, rejected = parse_fields(raw)
    assert fields == Fields(amount="49.90 EUR", reference="R-1")
    assert rejected == ["Belegdatum"]
    assert parse_fields(None) == (Fields(), [])
    assert parse_fields("Betrag 5 EUR") == (Fields(), ["fields"])


def test_parse_form_fields():
    form = {"f-0-amount": "12,30 EUR", "f-0-due_date": "2026-12-01", "f-0-reference": ""}
    assert parse_form_fields(form, "f-0-") == Fields(amount="12.30 EUR", due_date="2026-12-01")
    with pytest.raises(FieldError):
        parse_form_fields({"f-0-due_date": "morgen"}, "f-0-")


def test_fields_are_falsy_when_empty():
    assert not Fields() and Fields(reference="R-1")


# -- KI-Antwort ------------------------------------------------------------------------------------


def _answer(**fields):
    base = {"amount": None, "currency": None, "document_date": None, "reference": None, "due_date": None}
    return {"label": "privat/rechnungen", "confidence": 0.9, "reason": "Rechnung", "fields": base | fields}


def test_ai_fields_are_parsed(rules, make_mail):
    model = ScriptedModel("groq", _answer(amount=49.9, currency="EUR", reference="R-2026-17", due_date="2026-12-15"))
    c = AIClassifier(rules, model).classify(make_mail("Rechnung", "Betrag 49,90 EUR"))
    assert c.fields == Fields(amount="49.90 EUR", reference="R-2026-17", due_date="2026-12-15")
    assert c.reason == "KI (groq): Rechnung"


def test_invalid_ai_field_is_dropped_but_category_stays(rules, make_mail):
    model = ScriptedModel("groq", _answer(amount="sehr viel", reference="R-1"))
    c = AIClassifier(rules, model).classify(make_mail("Rechnung", ""))
    assert c.label == "privat/rechnungen"
    assert c.fields == Fields(reference="R-1") and "verworfen: Betrag" in c.reason


def test_unsure_answer_keeps_fields_for_the_human(rules, make_mail):
    answer = _answer(amount=10) | {"confidence": 0.3}
    c = AIClassifier(rules, ScriptedModel("groq", answer)).classify(make_mail())
    assert c.label == UNCLEAR and c.fields.amount == "10.00 EUR"


def test_schema_and_prompt_ask_for_fields(rules, make_mail):
    model = ScriptedModel("groq", _answer())
    clf = AIClassifier(rules, model)
    clf.classify(make_mail())
    system, _, schema = model.calls[0]
    assert schema["properties"]["fields"] == FIELDS_SCHEMA and "fields" in schema["required"]
    assert "Rate nie" in system and "JJJJ-MM-TT" in system
    json.dumps(schema)  # muss serialisierbar sein (geht an den Anbieter)


# -- PDF-Text --------------------------------------------------------------------------------------


def _pdf(text: str | None) -> bytes:
    """Minimales, gültiges PDF mit einer Seite; `None` erzeugt eine Seite ohne Text (wie ein Scan)."""
    stream = b"" if text is None else b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1") + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return out


def test_pdf_text_is_read():
    pytest.importorskip("pypdf")
    text = attachment_text(Attachment("Rechnung.pdf", _pdf("Rechnungsnummer RE-17 Betrag 49,90 EUR")))
    assert text is not None and "RE-17" in text and "49,90 EUR" in text


def test_pdf_without_text_and_broken_pdf_are_empty():
    pytest.importorskip("pypdf")
    assert attachment_text(Attachment("scan.pdf", _pdf(None))) == ""
    assert attachment_text(Attachment("kaputt.pdf", b"%PDF-1.4 kaputt")) == ""


def test_non_pdf_and_missing_package_give_none(monkeypatch):
    assert attachment_text(Attachment("foto.jpg", b"\xff\xd8")) is None
    import builtins

    real_import = builtins.__import__

    def no_pypdf(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    assert attachment_text(Attachment("Rechnung.pdf", _pdf("x"))) is None


def test_pdf_text_reaches_the_prompt(rules, make_mail):
    pytest.importorskip("pypdf")
    model = ScriptedModel("groq", _answer())
    mail = make_mail("Rechnung", "Anbei", attachments=[("Rechnung.pdf", _pdf("Kundennummer KD-4711"))])
    AIClassifier(rules, model).classify(mail)
    assert "Kundennummer KD-4711" in model.calls[0][1]


# -- Korrektur im Browser --------------------------------------------------------------------------

TOKEN = "t"


AI_FIELDS = Fields(amount="10.00 EUR")


def _review(rules, make_mail, fields=AI_FIELDS):
    mail = make_mail("Rechnung", "Zahlbar bis 15.12.2026.")
    clf = FixedClassifier({mail.id: Classification("privat/rechnungen", 0.9, "KI (groq): Rechnung", fields)})
    store = MemoryStore()
    return ReviewSession([mail], run([mail], clf, rules, store), rules, store, TOKEN)


def test_review_shows_fields_as_inputs(rules, make_mail):
    page = _review(rules, make_mail).page()
    assert 'name="f-0-amount" value="10.00 EUR"' in page and 'name="f-0-due_date" value=""' in page


def test_review_field_correction_is_applied(rules, make_mail):
    session = _review(rules, make_mail)
    form = {"token": TOKEN, "label-0": "privat/rechnungen", "f-0-amount": "12,50 EUR", "f-0-reference": "R-9"}
    result = session.approve(form)
    c = result.plans[0].classification
    assert c.fields == Fields(amount="12.50 EUR", reference="R-9")
    assert c.reason == CORRECTED and c.confidence == 0.9
    assert session.store.read_rows(result.plans[0].table)[0]["Betrag"] == "12.50 EUR"


def test_review_unchanged_fields_keep_ai_reason(rules, make_mail):
    session = _review(rules, make_mail)
    form = {"token": TOKEN, "f-0-amount": "10.00 EUR", "f-0-document_date": "", "f-0-reference": "", "f-0-due_date": ""}
    assert session.approve(form).plans[0].classification.reason == "KI (groq): Rechnung"


def test_review_invalid_field_writes_nothing(rules, make_mail):
    session = _review(rules, make_mail)
    with pytest.raises(ReviewError, match="Frist"):
        session.approve({"token": TOKEN, "f-0-due_date": "bald"})
    assert session.result is None and session.store.files == {}


def test_read_pdfs_false_keeps_attachments_local(rules):
    assert load_rules().ai.read_pdfs is True
    off = replace(rules, ai=replace(rules.ai, read_pdfs=False))
    creds = EnvCredentialStore({"PAPERPILOT_GROQ_API_KEY": "k"})
    clf = make_classifier("ai", off, creds)
    assert clf.ai.read_attachment(Attachment("Rechnung.pdf", _pdf("x"))) is None
    assert make_classifier("ai", rules, creds).ai.read_attachment is attachment_text
