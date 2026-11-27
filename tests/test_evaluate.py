"""Evaluation mit Angaben, Dev/Holdout, Verwechslungen und JSON (Roadmap 5)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from paperpilot_ops import cli
from paperpilot_ops.classify import FixedClassifier
from paperpilot_ops.composition import make_classifier
from paperpilot_ops.credentials import EnvCredentialStore
from paperpilot_ops.evaluate import evaluate, render_eval, select_split
from paperpilot_ops.models import Classification, Fields
from paperpilot_ops.sources import JsonSource

ROOT = Path(__file__).resolve().parents[1]


def _sample(id_, label, split="dev", fields=None):
    s = {"id": id_, "date": "2026-11-20T10:00", "from": "a@b.example", "subject": id_, "body": "", "label": label}
    s["split"] = split
    if fields is not None:
        s["fields"] = fields
    return s


SAMPLES = [
    _sample("a", "privat/rechnungen", fields={"amount": "49.90 EUR", "reference": "R-1", "due_date": "2026-12-01"}),
    _sample("b", "privat/rechnungen", "holdout", fields={"amount": "10.00 EUR"}),
    _sample("c", "werbung", fields={}),
]


def _classifier(**overrides):
    results = {
        "a": Classification("privat/rechnungen", 0.9, "", Fields(amount="49.90 EUR", reference="R-2")),
        "b": Classification("unklar", 0.2, "", Fields(amount="10.00 EUR", due_date="2026-12-24")),
        "c": Classification("werbung", 0.9),
    }
    return FixedClassifier(results | overrides)


def test_split_selection():
    assert [s["id"] for s in select_split(SAMPLES, "dev")] == ["a", "c"]
    assert [s["id"] for s in select_split(SAMPLES, "holdout")] == ["b"]
    assert len(select_split(SAMPLES, "all")) == 3
    assert select_split([{"id": "x"}], "dev") == [{"id": "x"}]  # ohne split zählt als dev
    with pytest.raises(ValueError):
        select_split(SAMPLES, "test")


def test_field_metrics_precision_and_recall():
    report = evaluate(_classifier(), SAMPLES)
    by_name = {f.name: f for f in report.fields}
    assert (by_name["Betrag"].correct, by_name["Betrag"].expected, by_name["Betrag"].predicted) == (2, 2, 2)
    assert by_name["Nummer"].precision == 0.0 and by_name["Nummer"].recall == 0.0  # R-2 statt R-1
    assert by_name["Frist"].recall == 0.0 and by_name["Frist"].precision == 0.0  # erfunden bzw. verpasst
    assert by_name["Belegdatum"].expected == 0


def test_confusion_and_render():
    report = evaluate(_classifier(), SAMPLES)
    assert report.confusion == {"privat/rechnungen": {"privat/rechnungen": 1, "unklar": 1}, "werbung": {"werbung": 1}}
    text = render_eval(report)
    assert "Verwechslungen" in text and "1 × privat/rechnungen" in text and "Betrag" in text
    holdout = evaluate(_classifier(), SAMPLES, "holdout")
    assert holdout.n == 1 and "Split: holdout" in render_eval(holdout)


def test_without_fields_no_field_table():
    report = evaluate(_classifier(), [_sample("c", "werbung")])
    assert report.fields == [] and "Angabe" not in render_eval(report)


def test_invalid_expected_field_is_reported():
    with pytest.raises(ValueError, match="Testset a"):
        evaluate(_classifier(), [_sample("a", "privat/rechnungen", fields={"amount": "viel"})])


def test_to_dict_is_json():
    data = json.loads(json.dumps(evaluate(_classifier(), SAMPLES).to_dict()))
    assert data["n"] == 3 and data["fields"][0]["name"] == "Betrag" and "confusion" in data


# -- mitgeliefertes Testset ------------------------------------------------------------------------


def _generator():
    spec = importlib.util.spec_from_file_location("make_testset", ROOT / "tools" / "make_testset.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_testset"] = module  # dataclasses brauchen das Modul in sys.modules
    spec.loader.exec_module(module)
    return module


def test_testset_matches_generator():
    assert _generator().main(["--check"]) == 0


def test_testset_shape():
    samples = JsonSource(cli._data("testset.jsonl")).load()
    assert len(samples) >= 200
    assert {s["split"] for s in samples} == {"dev", "holdout"}
    assert all(s["from"].split("@")[-1].rstrip(">").endswith((".example", "example.com")) for s in samples)
    # Holdout enthält nur Vorlagen, die in dev nicht vorkommen (Regel 9)
    dev = {s["template"] for s in samples if s["split"] == "dev"}
    assert not dev & {s["template"] for s in samples if s["split"] == "holdout"}
    assert sum("attachments" in s for s in samples) >= 20


def test_pdf_fields_are_readable_from_testset():
    pytest.importorskip("pypdf")
    from paperpilot_ops.pdftext import attachment_text
    from paperpilot_ops.sources import mail_from_dict

    samples = [s for s in JsonSource(cli._data("testset.jsonl")).load() if "attachments" in s and s["fields"]]
    mail = mail_from_dict(samples[0])
    text = attachment_text(mail.attachments[0])
    assert samples[0]["fields"]["reference"] in text


# -- CLI -------------------------------------------------------------------------------------------


def test_cli_eval_extended_testset_json(capsys):
    assert cli.main(["eval", "--testset", "angaben", "--split", "holdout", "--json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["split"] == "holdout" and data["n"] > 0 and len(data["fields"]) == 4
    assert "Sortiert mit" in captured.err


def test_cli_eval_single_provider(monkeypatch, capsys):
    seen = {}

    def fake_make(name, rules, creds):
        seen["chain"] = rules.ai.chain
        return make_classifier("rules", rules)

    monkeypatch.setattr(cli, "default_credential_store", lambda: EnvCredentialStore({}))
    monkeypatch.setattr(cli, "make_classifier", fake_make)
    assert cli.main(["eval", "--classifier", "ai", "--provider", "claude"]) == 0
    assert seen["chain"] == ("claude",)
