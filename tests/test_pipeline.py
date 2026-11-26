import csv

from paperpilot_ops.classify import RuleClassifier
from paperpilot_ops.pipeline import run
from paperpilot_ops.store import LocalStore


def _mails(make_mail):
    return [
        make_mail(
            "Einladung zum Interview",
            "Zu Ihrer Bewerbung als PM laden wir Sie am 03.12.2026 um 11:00 Uhr ein.",
            sender="HR <jobs@kranich.example>",
            date="2026-11-18T10:00",
        ),
        make_mail(
            "Ihre Rechnung",
            "Zahlbar bis 15.12.2026.",
            sender="<rechnung@stadtwerke.example>",
            date="2026-11-19T10:00",
            attachments=[("Rechnung.pdf", b"%PDF demo")],
        ),
        make_mail("Newsletter: 30 % Rabatt", "Jetzt sichern. Abmelden.", sender="<newsletter@shop.example>"),
        make_mail("Hallo", "Lange nicht gesehen", sender="Sam <sam@example.com>", date="2026-11-21T10:00"),
    ]


def test_dry_run_writes_nothing(tmp_path, rules, make_mail):
    result = run(_mails(make_mail), RuleClassifier(rules), rules, LocalStore(tmp_path))
    assert not result.applied
    assert list(tmp_path.iterdir()) == []
    assert [p.action for p in result.plans] == ["file", "file", "ignore", "review"]


def test_apply_files_tracks_and_is_idempotent(tmp_path, rules, make_mail):
    clf = RuleClassifier(rules)
    run(_mails(make_mail), clf, rules, LocalStore(tmp_path), apply=True)

    assert (tmp_path / "06 Rechnungen & Belege/2026/2026-11-19_Stadtwerke_Rechnung.pdf").exists()
    assert any((tmp_path / "Bewerbungen/Kranich").glob("2026-11-18_Kranich_Einladung-Interview.md"))
    assert any((tmp_path / "00 Eingang").iterdir())  # unklar -> Mensch prueft

    rows = list(csv.DictReader((tmp_path / "Bewerbungen/tracker.csv").open(encoding="utf-8")))
    assert rows[0]["firma"] == "Kranich" and rows[0]["status"] == "einladung"
    assert rows[0]["neu_aus_mail"].startswith("NEU 2026-11-18")

    ics = (tmp_path / "Fristen/fristen.ics").read_text()
    assert "20261203T110000" in ics and "20261215" in ics

    # Zweiter Lauf mit denselben Mails: alles schon da
    store = LocalStore(tmp_path)
    second = run(
        [m for m in _mails(make_mail) if store.last_run() is None or m.date > store.last_run()], clf, rules, store
    )
    assert second.plans == []
    third = run(_mails(make_mail), clf, rules, LocalStore(tmp_path))
    assert {p.action for p in third.plans} <= {"duplicate", "ignore"}


def test_never_overwrites(tmp_path):
    store = LocalStore(tmp_path)
    a = store.write_file("x/a.txt", b"1")
    b = store.write_file("x/a.txt", b"2")
    assert a.read_bytes() == b"1" and b.name == "a-2.txt"
